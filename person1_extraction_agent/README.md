# SimplifyNext — Review Handler AI Employee

Hackathon project. An AI "employee" for a small F&B business owner in Singapore
who reads their own reviews weekly and has no ops/analytics person.

**The problem:** they need to know which *specific, recurring operational issue is
getting worse* — not just which reviews are negative — and reviews come in
English, Chinese, Malay, and Tamil, which makes it easy to overreact to one loud
complaint and miss a quiet pattern building over weeks.

## Pipeline

```
raw review (any language)
   │
   ▼
[1] Extraction Agent      → structured record: language, translation, sentiment,
    (Haiku, Person 1)       topic (controlled vocab), entities, time slot
   │
   ▼
[2] Trend Detection Agent → clusters topics by ISO week, flags acceleration
    (Haiku + code, P2)      (3+ weeks strictly increasing, ≥2 latest week)
   │
   ▼
[3] Advice Agent          → one specific, actionable fix
    (Sonnet, P2)            ("staff the 12:00–13:30 slot", not "improve service")
   │
   ├─▶ [4] Reply Drafting Agent (Haiku, P3) → customer-facing reply in-language
   │
   ▼
Orchestration (LangGraph, P3) → Telegram: Monday 8am brief + tap-to-approve
```

## This repo = Person 1's slice

| deliverable | file |
|---|---|
| AWS / Bedrock Step 0 | `SETUP.md`, `.env.example`, `scripts/provision_aws.sh` |
| Data contract (locked Day 1) | `SCHEMA.md` |
| Pydantic models | `src/simplifynext/models.py` |
| Storage layer (local ⇄ DynamoDB/S3) | `src/simplifynext/repository.py` |
| Bedrock wrapper (+ offline mock) | `src/simplifynext/bedrock_client.py` |
| **Extraction Agent** | `src/simplifynext/extraction_agent.py` |
| CLI | `src/simplifynext/cli.py` |
| Synthetic multilingual reviews (with a planted trend) | `data/synthetic_reviews.json` |
| Offline tests | `tests/` |

## Quickstart (offline, no AWS)

```bash
cd simplifynext
uv sync
uv run simplifynext extract --input data/synthetic_reviews.json
uv run simplifynext show
uv run pytest
```

Then see `SETUP.md` to switch `LLM_PROVIDER=bedrock` / `STORAGE_BACKEND=dynamodb`.
