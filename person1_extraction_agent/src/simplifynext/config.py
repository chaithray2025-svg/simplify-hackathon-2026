"""Runtime config, loaded from environment / .env. No secrets live here."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Project root = two levels up from this file (src/simplifynext/config.py).
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
STORE_DIR = DATA_DIR / "store"


@dataclass(frozen=True)
class Settings:
    llm_provider: str            # "bedrock" | "mock"
    aws_profile: str
    aws_region: str
    model_extraction: str
    model_reasoning: str

    storage_backend: str         # "local" | "dynamodb"
    ddb_table_reviews: str
    ddb_table_trends: str
    ddb_table_advice: str
    ddb_table_replies: str
    ddb_table_feedback: str
    s3_bucket_raw: str

    @staticmethod
    def load() -> "Settings":
        return Settings(
            llm_provider=os.getenv("LLM_PROVIDER", "mock").strip().lower(),
            aws_profile=os.getenv("AWS_PROFILE", "workshop"),
            aws_region=os.getenv("AWS_DEFAULT_REGION", "ap-southeast-1"),
            # NOTE: this hackathon's AWS org has a Service Control Policy that
            # restricts Bedrock to the ap-southeast-1 region. Haiku 4.5 / Sonnet 4.5
            # only exist as cross-region inference profiles (global.*/apac.*), which
            # the SCP blocks regardless of Model access console settings. These
            # older on-demand IDs are confirmed working directly in ap-southeast-1 —
            # see SETUP.md "Model access" section before changing them.
            model_extraction=os.getenv(
                "BEDROCK_MODEL_EXTRACTION",
                "anthropic.claude-3-haiku-20240307-v1:0",
            ),
            model_reasoning=os.getenv(
                "BEDROCK_MODEL_REASONING",
                "anthropic.claude-3-5-sonnet-20240620-v1:0",
            ),
            storage_backend=os.getenv("STORAGE_BACKEND", "local").strip().lower(),
            ddb_table_reviews=os.getenv("DDB_TABLE_REVIEWS", "simplifynext_reviews"),
            ddb_table_trends=os.getenv("DDB_TABLE_TRENDS", "simplifynext_trends"),
            ddb_table_advice=os.getenv("DDB_TABLE_ADVICE", "simplifynext_advice"),
            ddb_table_replies=os.getenv("DDB_TABLE_REPLIES", "simplifynext_replies"),
            ddb_table_feedback=os.getenv("DDB_TABLE_FEEDBACK", "simplifynext_feedback"),
            s3_bucket_raw=os.getenv("S3_BUCKET_RAW", "simplifynext-raw-reviews"),
        )


SETTINGS = Settings.load()
