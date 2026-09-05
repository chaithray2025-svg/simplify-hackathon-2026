"""
LangGraph orchestration skeleton.

Per PROJECT_PLAN.md: state carries data through raw -> extracted -> (batched
weekly) -> trend flags -> advice -> (parallel) -> reply draft. Extraction,
Trend Detection, and Advice are Person 1/2's agents and don't exist yet, so
those stages are stubbed here as reads from `data_source.py` (mocked data
today, real DynamoDB later — see that file's docstring). Reply Drafting is
Person 3's own agent (`reply_drafting.py`) and is wired for real.

These are plain function nodes, not create_react_agent — per the plan, none
of these agents actually need to reason/loop, they're each single-shot calls,
so plain functions are simpler and cheaper than full ReAct agents.
"""

from typing import TypedDict

from langgraph.graph import StateGraph, START, END

import data_source
from reply_drafting import draft_reply
from telegram_brief import format_brief
from metrics import log_task_completion, log_loop_iteration


class PipelineState(TypedDict, total=False):
    trend_flags: list[dict]
    advice_by_trend: dict[str, dict]
    reviews_needing_reply: list[dict]
    reply_drafts: dict[str, str]
    briefs: list[str]


# --- Nodes --------------------------------------------------------------

def load_trends_and_advice(state: PipelineState) -> PipelineState:
    """
    STUB — stands in for Person 2's Trend Detection + Advice Agents.
    Swap this for reading real Trend Flag / Advice records once those
    agents exist (data_source.py already points at the right shape).
    """
    trend_flags = data_source.get_trend_flags()
    advice_by_trend = {
        tf["trend_flag_id"]: data_source.get_advice(tf["trend_flag_id"])
        for tf in trend_flags
    }
    return {"trend_flags": trend_flags, "advice_by_trend": advice_by_trend}


def draft_replies(state: PipelineState) -> PipelineState:
    """
    REAL — Person 3's Reply Drafting Agent, run over every review currently
    awaiting a reply.

    No retry logic exists yet, so each review is logged as a single bounded
    iteration (cap=1) per the "bound every loop" rule in PROJECT_PLAN.md —
    if retries are added later, bump `cap` accordingly and log each attempt.
    """
    reviews = data_source.get_reviews_needing_reply()
    drafts = {}
    for r in reviews:
        try:
            drafts[r["review_id"]] = draft_reply(r["review_text"], r["sentiment"], r["language"])
            log_loop_iteration(task_id=r["review_id"], iteration=1, cap=1)
            log_task_completion(task_id=f"reply:{r['review_id']}", completed=True)
        except Exception:
            log_task_completion(task_id=f"reply:{r['review_id']}", completed=False, human_intervened=True)
            raise
    return {"reviews_needing_reply": reviews, "reply_drafts": drafts}


def build_briefs(state: PipelineState) -> PipelineState:
    """
    REAL — Person 3's Telegram interface. Merges each Trend Flag with its
    Advice record into the JSON shape format_brief() expects, and renders
    the formatted message text for each.
    """
    briefs = []
    for tf in state["trend_flags"]:
        advice_record = state["advice_by_trend"][tf["trend_flag_id"]]
        merged = {**tf, **advice_record}  # trend flag fields + advice fields
        try:
            briefs.append(format_brief(merged))
            log_task_completion(task_id=f"brief:{tf['trend_flag_id']}", completed=True)
        except Exception:
            log_task_completion(task_id=f"brief:{tf['trend_flag_id']}", completed=False)
            raise
    return {"briefs": briefs}


# --- Graph ----------------------------------------------------------------

def build_graph():
    graph = StateGraph(PipelineState)

    graph.add_node("load_trends_and_advice", load_trends_and_advice)
    graph.add_node("draft_replies", draft_replies)
    graph.add_node("build_briefs", build_briefs)

    graph.add_edge(START, "load_trends_and_advice")
    graph.add_edge("load_trends_and_advice", "draft_replies")
    graph.add_edge("draft_replies", "build_briefs")
    graph.add_edge("build_briefs", END)

    return graph.compile()


if __name__ == "__main__":
    app = build_graph()
    result = app.invoke({})

    print("=== Reply drafts ===")
    for review_id, reply in result["reply_drafts"].items():
        print(f"[{review_id}] {reply}\n")

    print("=== Briefs ===")
    for brief in result["briefs"]:
        print(brief)
        print("---")