"""
metrics.py — lightweight instrumentation for the "Measuring Performance of
Digital AI Agents" judging criteria.

Design goal: bolt onto the existing agents with 1-2 line calls, no
restructuring. Every event is appended to a local JSON log
(mock_data/metrics_log.json by default — swap to DynamoDB later the same
way data_source.py does, nothing else needs to change).

Covers:
  1. Schema Validation Pass Rate  -> log_schema_validation()
  2. Tool-Call Success Rate       -> log_tool_call()
  3. Task Completion Rate         -> log_task_completion()
  4. Token Cost Per Run           -> log_token_usage()
  5. Loop Discipline              -> log_loop_iteration()
  6. Answer Fidelity              -> log_fidelity()

Call summary() (or run this file directly) to print judge-ready numbers.
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_LOG_PATH = os.environ.get(
    "METRICS_LOG_PATH", os.path.join(_THIS_DIR, "mock_data", "metrics_log.json")
)


# --- storage ----------------------------------------------------------------

def _load() -> list[dict]:
    if not os.path.exists(_LOG_PATH):
        return []
    with open(_LOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _append(event: dict) -> None:
    os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
    entries = _load()
    event["timestamp"] = time.time()
    entries.append(event)
    with open(_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)


# --- 1. Schema Validation Pass Rate -----------------------------------------

def log_schema_validation(record_type: str, passed: bool, reason: str | None = None) -> None:
    """Call this wherever a record is checked against SCHEMA.md's rules
    (e.g. Extraction Agent's Pydantic validation, rule 9)."""
    _append({
        "type": "schema_validation",
        "record_type": record_type,   # e.g. "ExtractedReviewRecord"
        "passed": passed,
        "reason": reason,
    })


# --- 2. Tool-Call Success Rate ----------------------------------------------

def log_tool_call(tool_name: str, success: bool, error: str | None = None) -> None:
    """Call around any external call the agent makes (Bedrock invoke, Telegram
    API, DynamoDB write, etc) — 'did the agent reach for the right hands?'"""
    _append({
        "type": "tool_call",
        "tool_name": tool_name,
        "success": success,
        "error": error,
    })


# --- 3. Task Completion Rate -------------------------------------------------

def log_task_completion(task_id: str, completed: bool, human_intervened: bool = False) -> None:
    """One call per pipeline run / per review processed end-to-end."""
    _append({
        "type": "task_completion",
        "task_id": task_id,
        "completed": completed,
        "human_intervened": human_intervened,
    })


# --- 4. Token Cost Per Run ---------------------------------------------------

def log_token_usage(
    step: str,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    run_id: str | None = None,
) -> None:
    """Call once per Bedrock call. For ChatBedrockConverse (langchain-aws),
    pull these from response.usage_metadata. For the raw boto3 `converse`
    call in bedrock_client.py, pull from response["usage"]."""
    _append({
        "type": "token_usage",
        "step": step,             # e.g. "trend_summary", "advice_agent"
        "model_id": model_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_creation_tokens": cache_creation_tokens,
        "run_id": run_id,
    })


# --- 5. Loop Discipline -------------------------------------------------------

def log_loop_iteration(task_id: str, iteration: int, cap: int) -> None:
    """Call once per retry/iteration of any bounded loop. 'Is it converging
    or circling?' — flags when a run hits its own cap."""
    _append({
        "type": "loop_iteration",
        "task_id": task_id,
        "iteration": iteration,
        "cap": cap,
        "hit_cap": iteration >= cap,
    })


# --- 6. Answer Fidelity --------------------------------------------------------

def log_fidelity(item_id: str, step: str, passed: bool, score: float | None = None, notes: str | None = None) -> None:
    """Call wherever output is checked against a rubric/ground truth — e.g.
    advice_agent.py's is_actionable() check is a binary fidelity check today."""
    _append({
        "type": "fidelity",
        "item_id": item_id,
        "step": step,
        "passed": passed,
        "score": score,
        "notes": notes,
    })


# --- summary ------------------------------------------------------------------

def summary() -> dict:
    entries = _load()
    by_type = defaultdict(list)
    for e in entries:
        by_type[e["type"]].append(e)

    out: dict = {}

    sv = by_type.get("schema_validation", [])
    if sv:
        out["schema_validation_pass_rate"] = sum(e["passed"] for e in sv) / len(sv)
        out["schema_validation_n"] = len(sv)

    tc = by_type.get("tool_call", [])
    if tc:
        out["tool_call_success_rate"] = sum(e["success"] for e in tc) / len(tc)
        out["tool_call_n"] = len(tc)

    task = by_type.get("task_completion", [])
    if task:
        out["task_completion_rate"] = sum(e["completed"] for e in task) / len(task)
        out["task_completion_n"] = len(task)
        out["task_human_intervention_rate"] = sum(e["human_intervened"] for e in task) / len(task)

    tok = by_type.get("token_usage", [])
    if tok:
        total_in = sum(e["input_tokens"] for e in tok)
        total_out = sum(e["output_tokens"] for e in tok)
        out["total_input_tokens"] = total_in
        out["total_output_tokens"] = total_out
        out["total_tokens"] = total_in + total_out
        out["token_usage_by_step"] = {
            step: {
                "input_tokens": sum(e["input_tokens"] for e in tok if e["step"] == step),
                "output_tokens": sum(e["output_tokens"] for e in tok if e["step"] == step),
            }
            for step in {e["step"] for e in tok}
        }

    loop = by_type.get("loop_iteration", [])
    if loop:
        out["max_loop_iteration"] = max(e["iteration"] for e in loop)
        out["loop_cap_hit_rate"] = sum(e["hit_cap"] for e in loop) / len(loop)

    fid = by_type.get("fidelity", [])
    if fid:
        out["fidelity_pass_rate"] = sum(e["passed"] for e in fid) / len(fid)
        out["fidelity_n"] = len(fid)
        scored = [e["score"] for e in fid if e.get("score") is not None]
        if scored:
            out["fidelity_avg_score"] = sum(scored) / len(scored)

    return out


if __name__ == "__main__":
    result = summary()
    if not result:
        print(f"No metrics logged yet at {_LOG_PATH}.")
    else:
        print(json.dumps(result, indent=2))