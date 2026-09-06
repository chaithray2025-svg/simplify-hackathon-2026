"""
Small reusable helper for calling Claude on Bedrock.

UPDATED (Person 1, verified live against the hackathon AWS account): this org
has a Service Control Policy restricting Bedrock to ap-southeast-1 ONLY. Haiku
4.5 only exists as a cross-region inference profile (us.*/global.*/apac.*),
which can route outside ap-southeast-1 — the SCP denies it regardless of what
region you set. us-east-1 will not work in this account at all.

Confirmed working directly in ap-southeast-1:

    LLM_PROVIDER=bedrock
    AWS_PROFILE=<your own profile name>
    AWS_DEFAULT_REGION=ap-southeast-1
    BEDROCK_MODEL=anthropic.claude-3-haiku-20240307-v1:0

Set these in your own .env (or shell) to match your local AWS profile name,
e.g.:

    AWS_PROFILE=hackathon
    AWS_DEFAULT_REGION=ap-southeast-1
    BEDROCK_MODEL=anthropic.claude-3-haiku-20240307-v1:0
"""

import os
import boto3
from dotenv import load_dotenv

from metrics import log_tool_call, log_token_usage

load_dotenv(".env")

AWS_PROFILE = os.environ.get("AWS_PROFILE", "hackathon")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "ap-southeast-1")
BEDROCK_MODEL = os.environ.get(
    "BEDROCK_MODEL", "anthropic.claude-3-haiku-20240307-v1:0"
)

# Built lazily, on first real call — NOT at import time. Building this eagerly
# meant `import reply_drafting` (and therefore `import orchestration`) crashed
# with botocore.exceptions.ProfileNotFound the instant AWS_PROFILE didn't match
# a configured profile (e.g. expired 12h SSO session, or just running `pytest`
# / exploring the code with no AWS set up at all) — before any Bedrock call was
# even attempted. Mirrors person1_extraction_agent/bedrock_client.py's pattern.
_client = None


def _get_client():
    global _client
    if _client is None:
        session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
        _client = session.client("bedrock-runtime")
    return _client


def ask_claude(prompt: str, system: str = "You are a helpful assistant.", max_tokens: int = 512) -> str:
    """Send one prompt to Claude via Bedrock, return the text reply."""
    try:
        response = _get_client().converse(
            modelId=BEDROCK_MODEL,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            system=[{"text": system}],
            inferenceConfig={"maxTokens": max_tokens},
        )
    except Exception as e:
        log_tool_call("bedrock_converse", success=False, error=str(e))
        raise

    log_tool_call("bedrock_converse", success=True)
    usage = response.get("usage", {})
    log_token_usage(
        step="ask_claude",
        model_id=BEDROCK_MODEL,
        input_tokens=usage.get("inputTokens", 0),
        output_tokens=usage.get("outputTokens", 0),
    )
    return response["output"]["message"]["content"][0]["text"]


if __name__ == "__main__":
    print(ask_claude("Say hello in 5 words or fewer."))