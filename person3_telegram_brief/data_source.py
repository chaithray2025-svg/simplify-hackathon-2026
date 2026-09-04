"""
Single point of contact for "where does the pipeline's data come from."

Right now this reads mocked JSON matching the expected record shapes (since
SCHEMA.md and the real DynamoDB tables don't exist yet — see PROJECT_PLAN.md).
Once Person 1 hands off the real DynamoDB tables, swap the bodies of these
three functions for real `boto3.client('dynamodb')` / resource calls — nothing
else in this codebase (orchestration, bot) needs to change, since they only
ever call these three functions.
"""

import json
import os

_DATA_DIR = os.path.join(os.path.dirname(__file__), "mock_data")


def get_trend_flags() -> list[dict]:
    """Trend Flag records (Person 2's Trend Detection Agent output)."""
    with open(os.path.join(_DATA_DIR, "trend_flags.json")) as f:
        return json.load(f)


def get_advice(trend_flag_id: str) -> dict:
    """Advice record for a given Trend Flag (Person 2's Advice Agent output)."""
    with open(os.path.join(_DATA_DIR, "advice.json")) as f:
        all_advice = json.load(f)
    return next(a for a in all_advice if a["trend_flag_id"] == trend_flag_id)


def get_reviews_needing_reply() -> list[dict]:
    """Individual reviews (with sentiment/language) awaiting a drafted reply."""
    with open(os.path.join(_DATA_DIR, "reviews_needing_reply.json")) as f:
        return json.load(f)
