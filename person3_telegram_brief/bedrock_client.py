"""
Small reusable helper for calling Claude on Bedrock, matching the config
Chaithra shared:

    LLM_PROVIDER=bedrock
    AWS_PROFILE=<your own profile name>
    AWS_DEFAULT_REGION=us-east-1
    BEDROCK_MODEL=us.anthropic.claude-haiku-4-5-20251001-v1:0

Set these in your own .env (or shell) to match your local AWS profile name,
e.g.:

    AWS_PROFILE=hackathon
    AWS_DEFAULT_REGION=us-east-1
    BEDROCK_MODEL=us.anthropic.claude-haiku-4-5-20251001-v1:0
"""

import os
import boto3
from dotenv import load_dotenv

load_dotenv(".env")

AWS_PROFILE = os.environ.get("AWS_PROFILE", "hackathon")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
BEDROCK_MODEL = os.environ.get(
    "BEDROCK_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
)

_session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
_client = _session.client("bedrock-runtime")


def ask_claude(prompt: str, system: str = "You are a helpful assistant.", max_tokens: int = 512) -> str:
    """Send one prompt to Claude via Bedrock, return the text reply."""
    response = _client.converse(
        modelId=BEDROCK_MODEL,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        system=[{"text": system}],
        inferenceConfig={"maxTokens": max_tokens},
    )
    return response["output"]["message"]["content"][0]["text"]


if __name__ == "__main__":
    print(ask_claude("Say hello in 5 words or fewer."))
