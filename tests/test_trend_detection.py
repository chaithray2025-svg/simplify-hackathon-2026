"""
tests/test_trend_detection.py

Automated tests for the acceleration rule and the chronic rule
(person2_trend_advice/trend_detection.py).

Run with: uv run pytest tests/test_trend_detection.py -v
(or: pytest tests/test_trend_detection.py -v, from the folder containing
trend_detection.py)
"""

import pytest

from trend_detection import (
    count_by_topic_week,
    detect_acceleration,
    detect_chronic,
    find_trend_flags,
)


# --- detect_acceleration: the core rule, tested directly on counts ----------

def test_strictly_increasing_3_weeks_flags():
    """The textbook positive case: 2 -> 3 -> 5, should flag."""
    counts = {"2026-W33": 2, "2026-W34": 3, "2026-W35": 5}
    flagged, detail = detect_acceleration(counts)
    assert flagged is True
    assert detail["weeks"] == ["2026-W33", "2026-W34", "2026-W35"]
    assert detail["counts"] == [2, 3, 5]


def test_flat_counts_do_not_flag():
    """No acceleration if the count isn't strictly increasing."""
    counts = {"2026-W33": 3, "2026-W34": 3, "2026-W35": 3}
    flagged, _ = detect_acceleration(counts)
    assert flagged is False


def test_decreasing_counts_do_not_flag():
    counts = {"2026-W33": 5, "2026-W34": 3, "2026-W35": 2}
    flagged, _ = detect_acceleration(counts)
    assert flagged is False


def test_noisy_non_monotonic_counts_do_not_flag():
    """Up-down-up shouldn't count as an accelerating trend."""
    counts = {"2026-W33": 2, "2026-W34": 1, "2026-W35": 4}
    flagged, _ = detect_acceleration(counts)
    assert flagged is False


def test_fewer_than_3_weeks_never_flags():
    """Rule requires 3+ consecutive weeks of history — 2 weeks is insufficient
    even if strictly increasing."""
    counts = {"2026-W34": 2, "2026-W35": 5}
    flagged, _ = detect_acceleration(counts)
    assert flagged is False


def test_latest_week_below_minimum_mentions_does_not_flag():
    """Strictly increasing but the latest week only has 1 mention — below the
    min_latest_mentions=2 floor, so it should NOT flag (avoids flagging noise
    like 0 -> 0 -> 1)."""
    counts = {"2026-W33": 0, "2026-W34": 0, "2026-W35": 1}
    flagged, _ = detect_acceleration(counts)
    assert flagged is False


def test_exactly_at_minimum_latest_mentions_flags():
    """Boundary case: latest week == min_latest_mentions (2) should flag."""
    counts = {"2026-W33": 0, "2026-W34": 1, "2026-W35": 2}
    flagged, _ = detect_acceleration(counts)
    assert flagged is True


def test_only_the_most_recent_window_is_considered():
    """A long history where the trend broke earlier shouldn't matter — only
    the most recent 3 consecutive weeks decide the flag. Here weeks
    W30-W32 accelerate then W33-W35 flatten, so this should NOT flag."""
    counts = {
        "2026-W30": 1, "2026-W31": 2, "2026-W32": 4,  # old acceleration, now over
        "2026-W33": 3, "2026-W34": 3, "2026-W35": 3,   # flat recently
    }
    flagged, detail = detect_acceleration(counts)
    assert flagged is False


def test_week_string_sorting_is_chronological_not_alphabetical():
    """W9 vs W10 sorts wrong alphabetically ('W10' < 'W9') unless weeks are
    zero-padded consistently. This guards against that class of bug by using
    a case where alphabetical sort would silently give the wrong order."""
    counts = {"2026-W09": 1, "2026-W10": 2, "2026-W11": 3}
    flagged, detail = detect_acceleration(counts)
    assert flagged is True
    assert detail["weeks"] == ["2026-W09", "2026-W10", "2026-W11"]


# --- detect_chronic: the persistence rule, tested directly on counts --------

def test_chronic_flags_flat_but_frequent_complaints():
    """The exact case detect_acceleration() is designed to ignore: same
    count every week, never rising. Should flag as chronic."""
    counts = {"2026-W33": 5, "2026-W34": 5, "2026-W35": 5}
    flagged, detail = detect_chronic(counts)
    assert flagged is True
    assert detail["average"] == 5.0


def test_chronic_flags_noisy_but_persistently_bad():
    """Non-monotonic counts that never accelerate but stay above threshold
    on average should still flag as chronic."""
    counts = {"2026-W33": 3, "2026-W34": 2, "2026-W35": 3}
    flagged, detail = detect_chronic(counts, min_avg_mentions=2.5)
    assert flagged is True
    assert round(detail["average"], 2) == 2.67


def test_chronic_does_not_flag_below_threshold():
    """Infrequent complaints, even if steady, shouldn't trip the chronic
    flag — mirrors detect_acceleration() ignoring single mentions."""
    counts = {"2026-W33": 1, "2026-W34": 1, "2026-W35": 1}
    flagged, _ = detect_chronic(counts)
    assert flagged is False


def test_chronic_requires_minimum_history():
    """Fewer than window_weeks of data shouldn't be enough to call something
    'chronic' — you need sustained history, not one good/bad week."""
    counts = {"2026-W34": 5, "2026-W35": 5}
    flagged, detail = detect_chronic(counts, window_weeks=3)
    assert flagged is False
    assert detail is None


def test_chronic_uses_only_most_recent_window():
    """An old bad patch that has since resolved shouldn't count — only the
    most recent `window_weeks` matter, mirroring detect_acceleration()'s
    'only the most recent window' behavior."""
    counts = {
        "2026-W30": 8, "2026-W31": 8,                  # old bad patch, since resolved
        "2026-W33": 1, "2026-W34": 1, "2026-W35": 1,    # now fine
    }
    flagged, detail = detect_chronic(counts, window_weeks=3)
    assert flagged is False


def test_chronic_boundary_at_exact_threshold():
    """Average exactly equal to min_avg_mentions should flag (>=, not >)."""
    counts = {"2026-W33": 3, "2026-W34": 3, "2026-W35": 3}
    flagged, detail = detect_chronic(counts, min_avg_mentions=3.0)
    assert flagged is True
    assert detail["average"] == 3.0


def test_topic_can_be_both_accelerating_and_chronic():
    """A topic that's been bad for weeks AND is now getting worse should be
    detectable by both rules independently — they're not mutually exclusive."""
    counts = {"2026-W33": 3, "2026-W34": 4, "2026-W35": 6}
    accel_flagged, _ = detect_acceleration(counts)
    chronic_flagged, _ = detect_chronic(counts, min_avg_mentions=3.0)
    assert accel_flagged is True
    assert chronic_flagged is True


# --- count_by_topic_week: grouping logic -------------------------------------

def test_count_by_topic_week_groups_correctly():
    reviews = [
        {"topic": "wait_time", "week": "2026-W33", "quote": "a", "date": "2026-08-15"},
        {"topic": "wait_time", "week": "2026-W33", "quote": "b", "date": "2026-08-16"},
        {"topic": "wait_time", "week": "2026-W34", "quote": "c", "date": "2026-08-22"},
        {"topic": "cleanliness", "week": "2026-W33", "quote": "d", "date": "2026-08-15"},
    ]
    counts = count_by_topic_week(reviews)
    assert counts["wait_time"]["2026-W33"] == 2
    assert counts["wait_time"]["2026-W34"] == 1
    assert counts["cleanliness"]["2026-W33"] == 1


def test_positive_sentiment_mentions_are_not_counted():
    """A topic that's mostly praised shouldn't accelerate- or chronic-flag
    just because people keep mentioning it favorably. Missing `sentiment`
    still defaults to counted (negative), for backward compatibility with
    fixtures/data that predate the sentiment field."""
    reviews = [
        {"topic": "food_quality", "week": "2026-W33", "sentiment": "positive", "quote": "great laksa", "date": "2026-08-15"},
        {"topic": "food_quality", "week": "2026-W34", "sentiment": "positive", "quote": "still great", "date": "2026-08-22"},
        {"topic": "food_quality", "week": "2026-W35", "sentiment": "positive", "quote": "amazing again", "date": "2026-08-29"},
        # one real complaint mixed into the same topic/weeks
        {"topic": "food_quality", "week": "2026-W35", "sentiment": "negative", "quote": "too salty this time", "date": "2026-08-29"},
    ]
    counts = count_by_topic_week(reviews)
    # only the single negative mention should be counted per week
    assert counts["food_quality"]["2026-W33"] == 0 or "2026-W33" not in counts["food_quality"]
    assert counts["food_quality"]["2026-W35"] == 1

    flags = find_trend_flags(reviews)
    assert flags == [], "positive-sentiment mentions must not produce a trend flag"


def test_supporting_quotes_exclude_positive_sentiment_even_when_topic_flags():
    """If a topic legitimately flags (real negative acceleration), any
    positive-sentiment review sharing the same topic/week must not leak
    into supporting_quotes as if it were evidence of the complaint."""
    reviews = []
    for week, n in [("2026-W33", 2), ("2026-W34", 3), ("2026-W35", 5)]:
        for i in range(n):
            reviews.append({"topic": "wait_time", "week": week, "sentiment": "negative",
                             "quote": f"slow-{week}-{i}", "date": "2026-08-15"})
    # a stray positive mention of the same topic in the flagged week
    reviews.append({"topic": "wait_time", "week": "2026-W35", "sentiment": "positive",
                     "quote": "actually fast today", "date": "2026-08-29"})

    flags = find_trend_flags(reviews)
    wait_time_flag = next(f for f in flags if f["topic"] == "wait_time")
    quotes = {q["quote"] for q in wait_time_flag["supporting_quotes"]}
    assert "actually fast today" not in quotes


# --- find_trend_flags: end-to-end on the planted-trend fixture --------------

@pytest.fixture
def planted_trend_reviews():
    """Mirrors the deliberate accelerating wait_time trend described in
    SETUP.md (W33=2 -> W34=3 -> W35=5), plus noise topics that must NOT flag."""
    reviews = []
    # wait_time: accelerating (2, 3, 5)
    for i in range(2):
        reviews.append({"topic": "wait_time", "week": "2026-W33", "quote": f"wt33-{i}", "date": "2026-08-15"})
    for i in range(3):
        reviews.append({"topic": "wait_time", "week": "2026-W34", "quote": f"wt34-{i}", "date": "2026-08-22"})
    for i in range(5):
        reviews.append({"topic": "wait_time", "week": "2026-W35", "quote": f"wt35-{i}", "date": "2026-08-29"})
    # cleanliness: flat, should not flag (avg well below chronic threshold too)
    for week in ["2026-W33", "2026-W34", "2026-W35"]:
        reviews.append({"topic": "cleanliness", "week": week, "quote": "clean", "date": "2026-08-15"})
    # food_quality: only 1 mention in latest week, should not flag
    reviews.append({"topic": "food_quality", "week": "2026-W35", "quote": "meh", "date": "2026-08-29"})
    return reviews


def test_find_trend_flags_flags_only_the_planted_trend(planted_trend_reviews):
    flags = find_trend_flags(planted_trend_reviews)
    flagged_topics = {f["topic"] for f in flags}

    assert "wait_time" in flagged_topics, "planted accelerating trend was not detected"
    assert "cleanliness" not in flagged_topics, "flat topic was incorrectly flagged"
    assert "food_quality" not in flagged_topics, "single-mention topic was incorrectly flagged"

    wait_time_flag = next(f for f in flags if f["topic"] == "wait_time")
    assert wait_time_flag["flag_type"] == "accelerating"
    assert wait_time_flag["weekly_counts"] == [2, 3, 5]
    assert len(wait_time_flag["supporting_quotes"]) == 5  # all latest-week (W35) quotes


# --- Stress test: two simultaneous trends, no cross-contamination -----------

@pytest.fixture
def two_trend_reviews():
    """Two independently accelerating trends running in the same window,
    plus noise topics that must stay unflagged. Guards against a bug class
    where grouping/counting accidentally mixes topics together, or where a
    second real trend gets masked by the first."""
    reviews = []

    # Trend 1: wait_time, 2 -> 3 -> 5
    for week, n in [("2026-W33", 2), ("2026-W34", 3), ("2026-W35", 5)]:
        for i in range(n):
            reviews.append({"topic": "wait_time", "week": week,
                             "quote": f"wt-{week}-{i}", "date": "2026-08-15"})

    # Trend 2: order_accuracy, 1 -> 2 -> 4 (different shape/magnitude on purpose,
    # so a bug that hardcodes wait_time's counts would fail this)
    for week, n in [("2026-W33", 1), ("2026-W34", 2), ("2026-W35", 4)]:
        for i in range(n):
            reviews.append({"topic": "order_accuracy", "week": week,
                             "quote": f"oa-{week}-{i}", "date": "2026-08-16"})

    # Noise: cleanliness flat, staff_attitude only 1 mention latest week
    for week in ["2026-W33", "2026-W34", "2026-W35"]:
        reviews.append({"topic": "cleanliness", "week": week, "quote": "clean", "date": "2026-08-15"})
    reviews.append({"topic": "staff_attitude", "week": "2026-W35", "quote": "rude", "date": "2026-08-29"})

    return reviews


def test_two_simultaneous_trends_both_detected_independently(two_trend_reviews):
    flags = find_trend_flags(two_trend_reviews)
    flagged_topics = {f["topic"] for f in flags}

    assert "wait_time" in flagged_topics
    assert "order_accuracy" in flagged_topics
    assert "cleanliness" not in flagged_topics
    assert "staff_attitude" not in flagged_topics
    assert len(flags) == 2, f"expected exactly 2 flags, got {len(flags)}: {flagged_topics}"

    wait_time_flag = next(f for f in flags if f["topic"] == "wait_time")
    order_accuracy_flag = next(f for f in flags if f["topic"] == "order_accuracy")

    # Each trend keeps its own counts — no bleed-through between topics.
    assert wait_time_flag["weekly_counts"] == [2, 3, 5]
    assert order_accuracy_flag["weekly_counts"] == [1, 2, 4]

    # Supporting quotes are topic-specific, not shared/duplicated across trends.
    wt_quotes = {q["quote"] for q in wait_time_flag["supporting_quotes"]}
    oa_quotes = {q["quote"] for q in order_accuracy_flag["supporting_quotes"]}
    assert wt_quotes.isdisjoint(oa_quotes)
    assert all(q.startswith("wt-") for q in wt_quotes)
    assert all(q.startswith("oa-") for q in oa_quotes)


# --- Stress test: a chronic-only trend alongside an accelerating one --------

@pytest.fixture
def chronic_and_accelerating_reviews():
    """One topic that's chronic-only (steady, never accelerating) alongside
    one that's accelerating-only, plus noise that must stay unflagged.
    Mirrors the real portion_size (chronic) vs wait_time (accelerating)
    split added to fake_extracted_reviews.json."""
    reviews = []

    # wait_time: accelerating (2, 3, 5)
    for week, n in [("2026-W01", 2), ("2026-W02", 3), ("2026-W03", 5)]:
        for i in range(n):
            reviews.append({"topic": "wait_time", "week": week,
                             "quote": f"wt-{week}-{i}", "date": "2026-01-01"})

    # portion_size: chronic-only (3, 2, 3 — steady, not strictly increasing)
    for week, n in [("2026-W01", 3), ("2026-W02", 2), ("2026-W03", 3)]:
        for i in range(n):
            reviews.append({"topic": "portion_size", "week": week,
                             "quote": f"ps-{week}-{i}", "date": "2026-01-01"})

    # cleanliness: flat and low, should stay unflagged by both rules
    for week in ["2026-W01", "2026-W02", "2026-W03"]:
        reviews.append({"topic": "cleanliness", "week": week, "quote": "clean", "date": "2026-01-01"})

    return reviews


def test_chronic_only_topic_flagged_separately_from_accelerating_topic(chronic_and_accelerating_reviews):
    flags = find_trend_flags(chronic_and_accelerating_reviews, chronic_min_avg_mentions=2.5)
    by_topic = {f["topic"]: f for f in flags}

    assert "wait_time" in by_topic
    assert by_topic["wait_time"]["flag_type"] == "accelerating"
    # wait_time's own average (2,3,5 -> 3.33) also clears the chronic
    # threshold here — it's genuinely both getting worse AND persistently
    # above the bar, which is a real and expected combination.
    assert by_topic["wait_time"]["chronic_also"] is True

    assert "portion_size" in by_topic
    assert by_topic["portion_size"]["flag_type"] == "chronic"
    assert by_topic["portion_size"]["chronic_also"] is False
    # chronic evidence spans the whole window, not just the latest week
    assert len(by_topic["portion_size"]["supporting_quotes"]) == 3 + 2 + 3

    assert "cleanliness" not in by_topic