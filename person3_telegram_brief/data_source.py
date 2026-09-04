"""
Single point of contact for "where does the pipeline's data come from."

Trend Flags + Advice now call Person 2's REAL agent code directly
(person2_trend_advice/), running against their fake_data dataset — this
is a real pipeline run (real Bedrock calls, real $ spend), not mocked
JSON, even though there's no DynamoDB yet. When Person 1's real
Extraction Agent + DynamoDB tables exist, swap `get_trend_flags()` /
`get_advice()` to read from DynamoDB instead of calling Person 2's code
against the fake dataset — nothing outside this file needs to change.

get_reviews_needing_reply() is still mocked (mock_data/) since it depends
on Person 1's Extraction Agent, which doesn't exist yet.
"""

import json
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_THIS_DIR, "mock_data")

# --- Wire in Person 2's real trend/advice code -----------------------------
# Assumes this file lives alongside person2_trend_advice/ in the repo (i.e.
# both are top-level folders in simplify-hackathon-2026/). When running from
# ~/ignite-hackathon during standalone dev, this path won't exist and the
# import is skipped — get_trend_flags()/get_advice() fall back to mock JSON.

_REPO_ROOT = os.path.dirname(_THIS_DIR)
_PERSON2_DIR = os.path.join(_REPO_ROOT, "person2_trend_advice")
_REVIEWS_PATH = os.path.join(_PERSON2_DIR, "fake_data", "fake_extracted_reviews.json")

_person2_available = os.path.isdir(_PERSON2_DIR)
if _person2_available:
    sys.path.insert(0, _PERSON2_DIR)
    from trend_detection import load_reviews, find_trend_flags  # noqa: E402
    from trend_summary import summarize_trend  # noqa: E402
    from advice_agent import generate_advice, is_actionable  # noqa: E402

# Simple in-process cache — these are real (billed) Bedrock calls, don't
# re-run them more than once per process just because multiple pipeline
# steps ask for the same trend flag.
_cache: dict = {}


def get_trend_flags() -> list[dict]:
    """Trend Flag records — Person 2's Trend Detection Agent output."""
    if not _person2_available:
        with open(os.path.join(_DATA_DIR, "trend_flags.json")) as f:
            return json.load(f)

    if "trend_flags" not in _cache:
        reviews = load_reviews(_REVIEWS_PATH)
        flags = find_trend_flags(reviews)
        for i, flag in enumerate(flags):
            flag["trend_flag_id"] = f"tf{i:03d}"
            flag["trend_summary"] = summarize_trend(flag)  # real Haiku call
        _cache["trend_flags"] = flags

    return _cache["trend_flags"]


def get_advice(trend_flag_id: str) -> dict:
    """Advice record for a given Trend Flag — Person 2's Advice Agent output."""
    if not _person2_available:
        with open(os.path.join(_DATA_DIR, "advice.json")) as f:
            all_advice = json.load(f)
        return next(a for a in all_advice if a["trend_flag_id"] == trend_flag_id)

    _cache.setdefault("advice", {})
    if trend_flag_id not in _cache["advice"]:
        flag = next(f for f in get_trend_flags() if f["trend_flag_id"] == trend_flag_id)
        advice_text = generate_advice(flag)  # real Sonnet call
        passed = is_actionable(advice_text)
        _cache["advice"][trend_flag_id] = {
            "trend_flag_id": trend_flag_id,
            "advice": advice_text,
            "actionability_check": "PASS" if passed else "FAIL",
        }

    return _cache["advice"][trend_flag_id]


def get_reviews_needing_reply() -> list[dict]:
    """Individual reviews (with sentiment/language) awaiting a drafted reply.
    Still mocked — depends on Person 1's Extraction Agent, not built yet."""
    with open(os.path.join(_DATA_DIR, "reviews_needing_reply.json")) as f:
        return json.load(f)
