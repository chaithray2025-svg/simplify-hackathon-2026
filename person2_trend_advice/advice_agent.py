"""
Advice Agent — Step 3: turn a Trend Flag into ONE specific, actionable fix.

This is the differentiator. Model: Sonnet (not Haiku) — this is a
reasoning step, not a formatting step. Few-shot examples do the heavy
lifting here: they teach the model the DIFFERENCE between generic
advice and specific advice, which a plain instruction alone won't
reliably produce.

Handles both flag types from trend_detection.py:
  - "accelerating": something getting worse over recent weeks
  - "chronic":       something persistently bad but not currently worsening
The fix itself must be equally specific and actionable either way — the
flag_type only changes how the model should understand urgency/framing,
not how careful the advice needs to be.
"""

import os
import re
from dotenv import load_dotenv
from langchain_aws import ChatBedrockConverse

from trend_detection import load_reviews, find_trend_flags
from metrics import log_token_usage, log_fidelity

load_dotenv()

# VERIFIED (Person 1, live against the hackathon account): this AWS org has a
# Service Control Policy that restricts Bedrock to ap-southeast-1 ONLY. Sonnet
# 4.5 only exists as a cross-region inference profile (us.*/global.*/apac.*),
# which by definition can route outside ap-southeast-1 — so the SCP denies it
# with "AccessDeniedException ... explicit deny in a service control policy",
# no matter the region you set here. us-east-1 will not work in this account.
# This on-demand ID is confirmed working directly in ap-southeast-1:
SONNET_MODEL_ID = os.environ.get(
    "BEDROCK_SONNET_MODEL", "anthropic.claude-3-5-sonnet-20240620-v1:0"
)
REGION = os.environ.get("AWS_DEFAULT_REGION", "ap-southeast-1")

# Built lazily, on first real call. ChatBedrockConverse constructs its own
# boto3 client at instantiation, which validates AWS credentials immediately —
# building it at import time meant `import advice_agent` (pulled in by
# data_source.py the moment person2_trend_advice/ exists on disk) crashed
# before any trend was ever generated, with no way to fall back to mock data.
_model = None


def _get_model():
    global _model
    if _model is None:
        _model = ChatBedrockConverse(
            model=SONNET_MODEL_ID,
            temperature=0,
            region_name=REGION,
        )
    return _model

SYSTEM_PROMPT = """You are an operations advisor for a small F&B business owner in Singapore.
You will be given a trending complaint topic, its flag type, the weekly counts behind it, and sample review quotes.

The flag type is one of:
- "accelerating": this complaint has been rising for 3+ consecutive weeks — it is getting worse right now.
- "chronic": this complaint has stayed frequent week after week without necessarily getting worse — it is a
  persistent, unresolved issue rather than a fresh spike.
Use the flag type only to understand the situation. It does NOT change how careful or specific your advice
needs to be — an accelerating trend and a chronic one both get ONE equally concrete fix.

Your job: write ONE sentence of advice that is SPECIFIC and ACTIONABLE.

Specific advice names one of: a time window, a staff role or shift, a named menu item,
or a concrete process change. It should be something the owner could act on TODAY without
asking a follow-up question.

Generic advice restates the problem as a goal ("improve service", "train staff better",
"pay more attention to X"). This is NOT useful and you must never produce it.

Here are examples of the difference:

---
Topic: wait_time (accelerating)
Quotes: "20 min wait for a table, only two staff on lunch shift", "Waited so long during lunch I almost left"
BAD: "Improve service speed during busy periods."
GOOD: "Add one extra staff member to the 12:00-13:30 lunch shift, which is named in the recent complaints."
---
Topic: order_accuracy (accelerating)
Quotes: "They gave me the wrong noodle dish twice this month", "Order mixed up again, got someone else's food"
BAD: "Be more careful when preparing orders."
GOOD: "Add a verbal order read-back step at the kitchen pass before dishes leave for the table."
---
Topic: cleanliness (accelerating)
Quotes: "Tables were sticky and not wiped between customers", "Floor near the entrance was dirty"
BAD: "Clean the restaurant more often."
GOOD: "Add a table-wipe-down check after every seating, logged on a checklist near the register."
---
Topic: portion_size (chronic)
Quotes: "Portion feels smaller than before", "Not enough food for the price anymore"
BAD: "Increase portion sizes."
GOOD: "Set a fixed scoop size for rice and gravy on this dish so every plate leaves the kitchen the same size."
---

Output ONLY the one sentence of advice. No preamble, no explanation."""


def generate_advice(trend_flag):
    flag_type = trend_flag.get("flag_type", "accelerating")

    user_content = f"""Topic: {trend_flag['topic']}
Flag type: {flag_type}
Weeks: {trend_flag['weeks']}
Weekly mention counts: {trend_flag['weekly_counts']}
Sample quotes:
{chr(10).join('- ' + q['quote'] for q in trend_flag['supporting_quotes'][:4])}
"""

    response = _get_model().invoke([
        ("system", SYSTEM_PROMPT),
        ("human", user_content),
    ])

    usage = response.usage_metadata or {}
    log_token_usage(
        step="advice_agent",
        model_id=SONNET_MODEL_ID,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        run_id=trend_flag.get("topic"),
    )

    return response.content


def is_actionable(advice_text):
    """
    Cheap, deterministic check: does the advice contain a time,
    a staff/role word, or a named item — something concrete?
    This is NOT a replacement for human judgment, just a first-pass filter.
    Same bar for accelerating and chronic advice — flag_type doesn't
    loosen the actionability requirement.
    """
    time_pattern = r"\b\d{1,2}(:\d{2})?\s*(am|pm|-)\b|\b\d{1,2}:\d{2}\b"
    role_words = ["staff", "cashier", "waiter", "waitress", "kitchen", "server", "chef", "shift"]
    process_words = ["checklist", "read-back", "log", "add a", "check", "set a", "fixed"]

    text_lower = advice_text.lower()
    has_time = bool(re.search(time_pattern, text_lower))
    has_role = any(w in text_lower for w in role_words)
    has_process = any(w in text_lower for w in process_words)

    return has_time or has_role or has_process


if __name__ == "__main__":
    reviews = load_reviews("fake_data/fake_extracted_reviews.json")
    flags = find_trend_flags(reviews)

    for flag in flags:
        advice = generate_advice(flag)
        passed = is_actionable(advice)
        log_fidelity(item_id=flag["topic"], step="advice_actionability", passed=passed)

        print(f"Topic: {flag['topic']} [{flag['flag_type']}]")
        print(f"Advice: {advice}")
        print(f"Actionability check: {'PASS' if passed else 'FAIL - too generic, retry or flag for review'}")
        print()