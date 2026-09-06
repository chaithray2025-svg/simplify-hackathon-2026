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


def _mock_trend_flags() -> list[dict]:
    with open(os.path.join(_DATA_DIR, "trend_flags.json")) as f:
        return json.load(f)


def _mock_advice(trend_flag_id: str) -> dict:
    """Look up `trend_flag_id` in the mock advice set. If it isn't there —
    e.g. real trend detection produced ids like "tf000" but only advice
    generation failed and fell back, so there's no mock entry under that
    exact id — reuse the first mock advice record's content under the id
    the caller actually asked for, rather than raising StopIteration and
    taking the whole run down over a demo-mode id mismatch."""
    with open(os.path.join(_DATA_DIR, "advice.json")) as f:
        all_advice = json.load(f)
    match = next((a for a in all_advice if a["trend_flag_id"] == trend_flag_id), None)
    if match is not None:
        return match
    template = dict(all_advice[0])
    template["trend_flag_id"] = trend_flag_id
    return template


def get_trend_flags() -> list[dict]:
    """Trend Flag records — Person 2's Trend Detection Agent output.

    Falls back to mock_data/trend_flags.json if the real Bedrock call fails
    for any reason (expired 12h SSO session, no AWS configured at all, etc.)
    so the rest of the pipeline — and a live demo — can still run. Without
    this, a stale AWS session took down the whole bot with it.
    """
    if not _person2_available:
        return _mock_trend_flags()

    if "trend_flags" not in _cache:
        try:
            reviews = load_reviews(_REVIEWS_PATH)
            flags = find_trend_flags(reviews)
            for i, flag in enumerate(flags):
                flag["trend_flag_id"] = f"tf{i:03d}"
                flag["trend_summary"] = summarize_trend(flag)  # real Haiku call
            _cache["trend_flags"] = flags
        except Exception as exc:  # noqa: BLE001 - deliberate offline fallback boundary
            print(f"[data_source] real trend detection failed ({exc}); "
                  f"falling back to mock_data/trend_flags.json", flush=True)
            _cache["trend_flags"] = _mock_trend_flags()

    return _cache["trend_flags"]


def get_advice(trend_flag_id: str) -> dict:
    """Advice record for a given Trend Flag — Person 2's Advice Agent output.

    Same fallback-to-mock rule as get_trend_flags() above.
    """
    if not _person2_available:
        return _mock_advice(trend_flag_id)

    _cache.setdefault("advice", {})
    if trend_flag_id not in _cache["advice"]:
        try:
            flag = next(f for f in get_trend_flags() if f["trend_flag_id"] == trend_flag_id)
            advice_text = generate_advice(flag)  # real Sonnet call
            passed = is_actionable(advice_text)
            _cache["advice"][trend_flag_id] = {
                "trend_flag_id": trend_flag_id,
                "advice": advice_text,
                "actionability_check": "PASS" if passed else "FAIL",
            }
        except Exception as exc:  # noqa: BLE001 - deliberate offline fallback boundary
            print(f"[data_source] real advice generation failed ({exc}); "
                  f"falling back to mock_data/advice.json", flush=True)
            _cache["advice"][trend_flag_id] = _mock_advice(trend_flag_id)

    return _cache["advice"][trend_flag_id]


def get_reviews_needing_reply() -> list[dict]:
    """Individual reviews (with sentiment/language) awaiting a drafted reply.
    Still mocked — depends on Person 1's Extraction Agent, not built yet."""
    with open(os.path.join(_DATA_DIR, "reviews_needing_reply.json")) as f:
        return json.load(f)
