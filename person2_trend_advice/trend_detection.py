"""
Trend Detection Agent — Step 1: the acceleration rule (+ chronic rule).

Rule 1 — ACCELERATING (locked by the team):
  A topic is flagged as an accelerating trend if its weekly mention count
  STRICTLY INCREASES across 3+ consecutive weeks, AND the latest week has
  at least 2 mentions.

Rule 2 — CHRONIC (added later, deliberately separate from Rule 1):
  A topic is flagged as chronic if its average weekly mention count over
  the most recent `chronic_window_weeks` weeks is at or above
  `chronic_min_avg_mentions` — regardless of whether it's rising, flat, or
  noisy. This exists specifically to catch what Rule 1 is designed to
  ignore: something frequent but never getting worse (e.g. 3, 2, 3).

Both rules are deterministic Python — no LLM call here. The LLM only gets
used afterward, to turn a flagged trend into a plain-English sentence
(trend_summary.py) and a fix (advice_agent.py).

A topic can end up:
  - accelerating only   -> flag_type = "accelerating"
  - chronic only         -> flag_type = "chronic"
  - both                 -> flag_type = "accelerating", chronic_also = True
    (accelerating wins the primary label since it's the more time-sensitive
    signal, but chronic_also is kept so downstream steps don't lose that
    context)
  - neither               -> not flagged at all
"""

import json
from collections import defaultdict

# Chronic rule defaults. Unlike the acceleration rule (which has no free
# parameter — "strictly increasing" is unambiguous), these are a judgment
# call and are the numbers to defend if asked "why 3 weeks / why 2.5?".
# Set to match the ~3-week windows used throughout the fake/demo dataset.
CHRONIC_WINDOW_WEEKS = 3
CHRONIC_MIN_AVG_MENTIONS = 2.5


def load_reviews(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def count_by_topic_week(reviews, only_negative=True):
    """
    Returns: { topic: { week: count } }

    By default, only counts NEGATIVE-sentiment mentions. Without this, a
    topic that's overwhelmingly praised (e.g. food_quality reviews that are
    all "positive") would be counted the same as genuine complaints, and
    could theoretically accelerate- or chronic-flag as if it were a problem
    getting worse, purely because people keep mentioning it favorably.

    Backward compatible with review records that don't include a
    `sentiment` field at all (older test fixtures, some fake data) —
    missing sentiment defaults to "negative" so those records are still
    counted exactly as before.
    """
    counts = defaultdict(lambda: defaultdict(int))
    for r in reviews:
        if only_negative and r.get("sentiment", "negative") != "negative":
            continue
        counts[r["topic"]][r["week"]] += 1
    return counts


def sorted_weeks(week_counts):
    """Sort week strings like '2026-W03' correctly (chronological, not alphabetical-by-accident)."""
    return sorted(week_counts.keys())


def detect_acceleration(week_counts, min_weeks=3, min_latest_mentions=2):
    """
    week_counts: { week: count } for a single topic
    Returns True if the mention count strictly increases across the
    most recent `min_weeks` consecutive weeks, and the latest week
    has at least `min_latest_mentions`.
    """
    weeks = sorted_weeks(week_counts)
    if len(weeks) < min_weeks:
        return False, None

    recent_weeks = weeks[-min_weeks:]
    recent_counts = [week_counts[w] for w in recent_weeks]

    is_increasing = all(
        recent_counts[i] < recent_counts[i + 1]
        for i in range(len(recent_counts) - 1)
    )
    latest_count = recent_counts[-1]

    if is_increasing and latest_count >= min_latest_mentions:
        return True, {
            "weeks": recent_weeks,
            "counts": recent_counts,
        }
    return False, None


def detect_chronic(week_counts, window_weeks=CHRONIC_WINDOW_WEEKS, min_avg_mentions=CHRONIC_MIN_AVG_MENTIONS):
    """
    week_counts: { week: count } for a single topic

    Flags a topic as CHRONIC if the average weekly mention count over the
    most recent `window_weeks` weeks is >= `min_avg_mentions` — independent
    of direction. This is the "has this just always been bad?" check,
    separate from "is this getting worse?" (detect_acceleration).

    Requires at least `window_weeks` weeks of history to fire at all — a
    topic with only 1-2 weeks of data can't be called chronic yet.

    Returns (flagged: bool, detail: dict | None), same shape convention as
    detect_acceleration — detail is None when not flagged.
    """
    weeks = sorted_weeks(week_counts)
    if len(weeks) < window_weeks:
        return False, None

    recent_weeks = weeks[-window_weeks:]
    recent_counts = [week_counts[w] for w in recent_weeks]
    avg = sum(recent_counts) / len(recent_counts)

    if avg >= min_avg_mentions:
        return True, {
            "weeks": recent_weeks,
            "counts": recent_counts,
            "average": round(avg, 2),
        }
    return False, None


def find_trend_flags(reviews, chronic_window_weeks=CHRONIC_WINDOW_WEEKS, chronic_min_avg_mentions=CHRONIC_MIN_AVG_MENTIONS):
    """
    Runs both the acceleration rule and the chronic rule over every topic
    in the dataset. Returns a list of Trend Flag records (matching
    SCHEMA.md shape, minus the LLM-generated summary sentence which comes
    later), each tagged with flag_type.
    """
    by_topic = count_by_topic_week(reviews)
    flags = []

    for topic, week_counts in by_topic.items():
        accel_flagged, accel_detail = detect_acceleration(week_counts)
        chronic_flagged, chronic_detail = detect_chronic(
            week_counts,
            window_weeks=chronic_window_weeks,
            min_avg_mentions=chronic_min_avg_mentions,
        )

        if not accel_flagged and not chronic_flagged:
            continue

        if accel_flagged:
            # Accelerating is the more time-sensitive signal, so it takes
            # the primary label even if chronic also fired. Evidence is the
            # latest week only — same behavior as before this change.
            flag_type = "accelerating"
            weeks = accel_detail["weeks"]
            weekly_counts = accel_detail["counts"]
            latest_week = weeks[-1]
            supporting_quotes = [
                {"quote": r["quote"], "date": r["date"]}
                for r in reviews
                if r["topic"] == topic and r["week"] == latest_week
                and r.get("sentiment", "negative") == "negative"
            ]
        else:
            # Chronic only: there's no single "latest spike" week to point
            # to — the evidence is the whole window being steadily bad, so
            # pull quotes from every week in the window.
            flag_type = "chronic"
            weeks = chronic_detail["weeks"]
            weekly_counts = chronic_detail["counts"]
            chronic_weeks = set(weeks)
            supporting_quotes = [
                {"quote": r["quote"], "date": r["date"]}
                for r in reviews
                if r["topic"] == topic and r["week"] in chronic_weeks
                and r.get("sentiment", "negative") == "negative"
            ]

        flags.append({
            "topic": topic,
            "flag_type": flag_type,
            "chronic_also": bool(accel_flagged and chronic_flagged),
            "weeks": weeks,
            "weekly_counts": weekly_counts,
            "supporting_quotes": supporting_quotes,
        })

    return flags


if __name__ == "__main__":
    reviews = load_reviews("fake_data/fake_extracted_reviews.json")
    flags = find_trend_flags(reviews)

    print(f"Loaded {len(reviews)} fake reviews.\n")

    if not flags:
        print("No trends flagged. Something's wrong — 'wait_time' should have flagged.")
    else:
        for f in flags:
            label = f["flag_type"].upper()
            if f["chronic_also"]:
                label += " (also chronic)"
            print(f"FLAGGED [{label}]: {f['topic']}")
            print(f"  weeks:  {f['weeks']}")
            print(f"  counts: {f['weekly_counts']}")
            print(f"  supporting quotes:")
            for q in f["supporting_quotes"]:
                print(f"    - \"{q['quote']}\" ({q['date']})")
            print()

    print("Sanity check — topics NOT flagged (expected: food_quality, cleanliness, staff_attitude):")
    flagged_topics = {f["topic"] for f in flags}
    all_topics = {r["topic"] for r in reviews}
    for t in sorted(all_topics - flagged_topics):
        print(f"  - {t} (correctly not flagged)")