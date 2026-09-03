"""
Trend Detection Agent — Step 1: the acceleration rule.

Rule (locked by the team):
  A topic is flagged as an accelerating trend if its weekly mention count
  STRICTLY INCREASES across 3+ consecutive weeks, AND the latest week has
  at least 2 mentions.

This is deterministic Python — no LLM call here. The LLM only gets used
afterward, to turn a flagged trend into a plain-English sentence.
"""

import json
from collections import defaultdict


def load_reviews(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def count_by_topic_week(reviews):
    """
    Returns: { topic: { week: count } }
    """
    counts = defaultdict(lambda: defaultdict(int))
    for r in reviews:
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


def find_trend_flags(reviews):
    """
    Runs the acceleration rule over every topic in the dataset.
    Returns a list of Trend Flag records (matching SCHEMA.md shape,
    minus the LLM-generated summary sentence which comes later).
    """
    by_topic = count_by_topic_week(reviews)
    flags = []

    for topic, week_counts in by_topic.items():
        flagged, detail = detect_acceleration(week_counts)
        if flagged:
            latest_week = detail["weeks"][-1]
            supporting_quotes = [
                {"quote": r["quote"], "date": r["date"]}
                for r in reviews
                if r["topic"] == topic and r["week"] == latest_week
            ]
            flags.append({
                "topic": topic,
                "weeks": detail["weeks"],
                "weekly_counts": detail["counts"],
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
            print(f"FLAGGED: {f['topic']}")
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
