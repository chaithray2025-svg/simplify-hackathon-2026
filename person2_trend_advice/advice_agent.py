"""
Advice Agent — Step 3: turn a Trend Flag into ONE specific, actionable fix.

This is the differentiator. Model: Sonnet (not Haiku) — this is a
reasoning step, not a formatting step. Few-shot examples do the heavy
lifting here: they teach the model the DIFFERENCE between generic
advice and specific advice, which a plain instruction alone won't
reliably produce.
"""

import os
import re
from dotenv import load_dotenv
from langchain_aws import ChatBedrockConverse

from trend_detection import load_reviews, find_trend_flags

load_dotenv()

# NOTE: swap this for your Sonnet inference profile ID once you've
# confirmed it the same way we confirmed Haiku's — run:
#   aws bedrock list-inference-profiles --profile <you> --region us-east-1 | grep -A 2 "sonnet-4"
SONNET_MODEL_ID = os.environ.get(
    "BEDROCK_SONNET_MODEL", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
)
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

model = ChatBedrockConverse(
    model=SONNET_MODEL_ID,
    temperature=0,
    region_name=REGION,
)

SYSTEM_PROMPT = """You are an operations advisor for a small F&B business owner in Singapore.
You will be given a trending complaint topic, the weekly counts behind it, and sample review quotes.

Your job: write ONE sentence of advice that is SPECIFIC and ACTIONABLE.

Specific advice names one of: a time window, a staff role or shift, a named menu item,
or a concrete process change. It should be something the owner could act on TODAY without
asking a follow-up question.

Generic advice restates the problem as a goal ("improve service", "train staff better",
"pay more attention to X"). This is NOT useful and you must never produce it.

Here are examples of the difference:

---
Topic: wait_time
Quotes: "20 min wait for a table, only two staff on lunch shift", "Waited so long during lunch I almost left"
BAD: "Improve service speed during busy periods."
GOOD: "Add one extra staff member to the 12:00-13:30 lunch shift, which is named in the recent complaints."
---
Topic: order_accuracy
Quotes: "They gave me the wrong noodle dish twice this month", "Order mixed up again, got someone else's food"
BAD: "Be more careful when preparing orders."
GOOD: "Add a verbal order read-back step at the kitchen pass before dishes leave for the table."
---
Topic: cleanliness
Quotes: "Tables were sticky and not wiped between customers", "Floor near the entrance was dirty"
BAD: "Clean the restaurant more often."
GOOD: "Add a table-wipe-down check after every seating, logged on a checklist near the register."
---

Output ONLY the one sentence of advice. No preamble, no explanation."""


def generate_advice(trend_flag):
    user_content = f"""Topic: {trend_flag['topic']}
Weeks: {trend_flag['weeks']}
Weekly mention counts: {trend_flag['weekly_counts']}
Sample quotes:
{chr(10).join('- ' + q['quote'] for q in trend_flag['supporting_quotes'][:4])}
"""

    response = model.invoke([
        ("system", SYSTEM_PROMPT),
        ("human", user_content),
    ])

    return response.content


def is_actionable(advice_text):
    """
    Cheap, deterministic check: does the advice contain a time,
    a staff/role word, or a named item — something concrete?
    This is NOT a replacement for human judgment, just a first-pass filter.
    """
    time_pattern = r"\b\d{1,2}(:\d{2})?\s*(am|pm|-)\b|\b\d{1,2}:\d{2}\b"
    role_words = ["staff", "cashier", "waiter", "waitress", "kitchen", "server", "chef", "shift"]
    process_words = ["checklist", "read-back", "log", "add a", "check"]

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

        print(f"Topic: {flag['topic']}")
        print(f"Advice: {advice}")
        print(f"Actionability check: {'PASS' if passed else 'FAIL - too generic, retry or flag for review'}")
        print()
