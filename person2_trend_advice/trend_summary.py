"""
Trend Detection Agent — Step 2: plain-English summary via Bedrock Haiku.

Takes a flagged trend (from trend_detection.py) and asks Haiku to write
one clear sentence for the owner's Telegram brief. Single call,
temperature=0, no tools — this is not a reasoning task, just formatting.
"""

import os
import json
from dotenv import load_dotenv
from langchain_aws import ChatBedrockConverse

from trend_detection import load_reviews, find_trend_flags
from metrics import log_token_usage

load_dotenv()

# VERIFIED (Person 1, live against the hackathon AWS account, see SETUP.md /
# bedrock_client.py): this org's SCP restricts Bedrock to ap-southeast-1 ONLY.
# Haiku 4.5 only exists here as a cross-region inference profile
# (us.*/global.*/apac.*), which the SCP denies regardless of region set here.
# us-east-1 + the *-4-5-* profile ID will NOT work in this account — use the
# same on-demand model + region as bedrock_client.py / advice_agent.py.
MODEL_ID = os.environ.get("BEDROCK_MODEL", "anthropic.claude-3-haiku-20240307-v1:0")
REGION = os.environ.get("AWS_DEFAULT_REGION", "ap-southeast-1")

model = ChatBedrockConverse(
    model=MODEL_ID,
    temperature=0,
    region_name=REGION,
)

SYSTEM_PROMPT = """You are writing one sentence for a small business owner's weekly review brief.
You will be given a topic, the weekly mention counts behind it, and a few sample quotes.
Write ONE plain-English sentence stating what is getting worse and how many weeks it's been rising.
Do not invent numbers or details not given to you. Do not add advice — that's a separate step.
Output ONLY the sentence, nothing else."""


def summarize_trend(trend_flag):
    user_content = f"""Topic: {trend_flag['topic']}
Weeks: {trend_flag['weeks']}
Weekly mention counts: {trend_flag['weekly_counts']}
Sample quotes:
{chr(10).join('- ' + q['quote'] for q in trend_flag['supporting_quotes'][:3])}
"""

    response = model.invoke([
        ("system", SYSTEM_PROMPT),
        ("human", user_content),
    ])

    usage = response.usage_metadata or {}
    log_token_usage(
        step="trend_summary",
        model_id=MODEL_ID,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        run_id=trend_flag.get("topic"),
    )

    return response.content


if __name__ == "__main__":
    reviews = load_reviews("fake_data/fake_extracted_reviews.json")
    flags = find_trend_flags(reviews)

    for flag in flags:
        summary = summarize_trend(flag)
        print(f"Topic: {flag['topic']}")
        print(f"Summary: {summary}\n")
