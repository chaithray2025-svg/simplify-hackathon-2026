# MakanReview

**An AI employee for your F&B stall.** It reads every review across platforms, tells you the *one* complaint that's actually getting worse — not just loud — writes the fix, drafts the reply, and sends it all in one weekly Telegram message.

Built for **SimplifyNext Hackathon 2026** by **Team ChaxGPT**: Agnella Agrata, Amirah Nufah Aulya, Chaithra Yerramsetty.

---

## The problem

3,047 F&B businesses closed in Singapore in 2024 — the most in almost two decades — and 82% of those that closed within five years never turned a profit. Meanwhile 94% of diners read reviews before choosing where to eat. A hawker-stall owner doesn't need another dashboard; they need to know which recurring complaint is *accelerating*, and one specific thing to do about it today, without reading every review between serving customers.

## What it does

Five agents, ending in one weekly message. The owner still decides.

| Step | Agent | What it does | Model |
|---|---|---|---|
| 1 | **Extraction** | Raw review (EN/中文/தமிழ்/Malay) → topic, sentiment, dish, staff role, time of day | Haiku |
| 2 | **Trend Detection** | Counts negative mentions per topic per week; flags only when a topic rises 3+ consecutive weeks | Python (deterministic) + Haiku for the summary line |
| 3 | **Advice** | Turns a flagged trend into one fix naming a time, role, or dish — never "improve service" | Sonnet |
| 4 | **Reply Drafting** | Drafts a reply in the customer's own language | Haiku |
| 5 | **Telegram** | One weekly message; owner taps Approve/Reject, every tap logged | Telegram Bot API |

**The differentiator:** acceleration, not volume. A topic that's frequent-but-flat, or spiky with no slope, stays quiet. The owner only hears about what's *building*.

## Architecture & ownership

```
Extraction (Track A) → Trend Detection (Track B) → Advice (Track B) → Reply Drafting (Track C) → Telegram (Track C)
```

| Person | Owns |
|---|---|
| **Person 1** | AWS/Bedrock setup, Extraction Agent, DynamoDB/S3 schema |
| **Person 2** | Trend Detection Agent + Advice Agent (the differentiator) |
| **Person 3** | Reply Drafting Agent, LangGraph orchestration, Telegram bot |

Full day-by-day plan and rationale: [`PROJECT_PLAN.md`](./PROJECT_PLAN.md). Data contract for the Extracted Review Record and Trend Flag: [`person1_extraction_agent/SCHEMA.md`](./person1_extraction_agent/SCHEMA.md).

## Repo structure

```
.
├── PROJECT_PLAN.md
├── person1_extraction_agent/       # Track A — Extraction
│   ├── SCHEMA.md                   # data contract all tracks build against
│   ├── SETUP.md                    # AWS/Bedrock setup (source of truth — see below)
│   ├── src/simplifynext/           # bedrock_client, extraction_agent, models, topics, cli
│   ├── data/                       # synthetic + golden + edge-case review fixtures
│   └── tests/
├── person2_trend_advice/           # Track B — Trend Detection + Advice (differentiator)
│   ├── trend_detection.py          # deterministic acceleration rule
│   ├── trend_summary.py            # Haiku-generated human-readable summary
│   ├── advice_agent.py             # Sonnet, few-shot, actionability-checked
│   └── fake_data/
├── person3_telegram_brief/         # Track C — Reply Drafting + Orchestration + Bot
│   ├── orchestration.py            # LangGraph pipeline
│   ├── reply_drafting.py
│   ├── telegram_brief.py / send_telegram.py / bot_listener.py
│   └── mock_data/
└── tests/                          # cross-cutting tests (trend detection acceleration rule)
```

## Setup

AWS access is via IAM Identity Center SSO (see `person1_extraction_agent/SETUP.md` for the full walkthrough). Condensed version:

1. `aws configure sso` once per teammate — SSO start URL from the hackathon training deck, SSO region `ap-southeast-1`, region `ap-southeast-1`, profile name `workshop`.
2. `aws sso login --profile workshop`, then verify with `aws sts get-caller-identity --profile workshop` (sessions expire — re-run login if this errors, especially before a demo).
3. `.env`:
   ```
   LLM_PROVIDER=bedrock
   AWS_PROFILE=workshop
   AWS_DEFAULT_REGION=ap-southeast-1
   BEDROCK_MODEL_EXTRACTION=anthropic.claude-3-haiku-20240307-v1:0
   BEDROCK_MODEL_REASONING=anthropic.claude-3-5-sonnet-20240620-v1:0
   ```
   > Note: cross-region inference profiles (`us.*`/`global.*`/`apac.*`) are blocked by an org-level SCP restricting Bedrock to `ap-southeast-1`. Use direct on-demand model IDs in that region, as above — confirmed working and used by every agent in this repo.
4. Install dependencies: `person1_extraction_agent` uses `uv` (`uv sync`), `person3_telegram_brief` uses pip (`pip install -r requirements.txt`).

**Storage backend:** `STORAGE_BACKEND` in `.env` toggles between:
- `local` (default) — reads/writes JSON files in `data/store/`, no AWS needed, $0 cost. Good for local dev and testing without touching the shared account.
- `dynamodb` — real tables in `AWS_DEFAULT_REGION` (`simplifynext_reviews`, `simplifynext_trends`, `simplifynext_advice`, `simplifynext_replies`, `simplifynext_feedback`), plus an S3 bucket (`simplifynext-raw-reviews`) for raw review payloads.

**Budget discipline:** $20 hard cap, team-wide, doesn't reset. Bedrock on-demand, Lambda, DynamoDB on-demand, and S3 only — no OpenSearch, SageMaker real-time endpoints, NAT Gateways, load balancers, always-on EC2/RDS, or Provisioned Throughput.

## Running the tests

The deterministic pieces are safe to run live (no API calls, no network risk):

```bash
pytest tests/test_trend_detection.py -v          # acceleration rule — 20 assertions
pytest person1_extraction_agent/tests/ -v         # schema validation
```

These back the numbers in the pitch deck: 22/22 extracted records pass schema validation, 22 unit tests pass across both suites (including the two-simultaneous-trends stress case and the W09/W10 chronological-sort edge case).

The full pipeline (extraction → trend → advice → reply → Telegram) makes live Bedrock calls and is demoed via recorded footage rather than live, to avoid venue wifi/latency risk.

## Current status

- Trend Detection + Advice pipeline (Person 2): built and tested — acceleration rule, Haiku trend summaries, Sonnet advice with actionability checks all passing.
- Extraction (Person 1) and Reply Drafting/Orchestration/Telegram (Person 3): built per the architecture above.
- **Not yet done:** one live run carrying a single review all the way from extraction to the Telegram message. Each track is verified independently against the shared schema; full end-to-end wiring is the next step.

## Roadmap

- Wire the full end-to-end pipeline (raw review → Telegram) into one runnable path.
- Price advice against runway (e.g. "one extra lunch runner costs ~$600/month against your $18k fixed costs").
- Additional review sources, a reverse rule that catches what's *improving*, multi-outlet view for small chains.