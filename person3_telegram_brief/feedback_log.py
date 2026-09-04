"""
Feedback log — records approve/reject taps on drafted replies.

This is the answer to the "not as accurate as humans" concern (per
PROJECT_PLAN.md): every drafted reply's fate (approved / rejected) is
logged, even if nothing downstream consumes it yet.

Like data_source.py, this writes to a local JSON file today. Swap
`log_feedback()` / `get_feedback()` for real DynamoDB writes/reads once
Person 1's tables exist — nothing else in the codebase needs to change.
"""

import json
import os
import time

_LOG_PATH = os.path.join(os.path.dirname(__file__), "mock_data", "feedback_log.json")


def _load() -> list[dict]:
    if not os.path.exists(_LOG_PATH):
        return []
    with open(_LOG_PATH) as f:
        return json.load(f)


def _save(entries: list[dict]) -> None:
    with open(_LOG_PATH, "w") as f:
        json.dump(entries, f, indent=2)


def log_feedback(review_id: str, decision: str, chat_id: str | None = None) -> None:
    """decision should be 'approved' or 'rejected'."""
    entries = _load()
    entries.append(
        {
            "review_id": review_id,
            "decision": decision,
            "chat_id": chat_id,
            "timestamp": int(time.time()),
        }
    )
    _save(entries)


def get_feedback() -> list[dict]:
    return _load()
