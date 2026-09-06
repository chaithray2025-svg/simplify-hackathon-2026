# Project Plan — Simplify Hackathon 2026

## ⚠️ Known gap: SCHEMA.md doesn't exist yet

This plan (and the agent steps below) repeatedly reference `SCHEMA.md` for the
Extracted Review Record and Trend Flag record shapes. **That file isn't in the
repo yet.** Person 1 owns the DynamoDB/S3 schema per the split below — this
needs to be written and committed before Persons 2 and 3 can build against a
stable contract. Until then, `person2_trend_advice/fake_data/fake_extracted_reviews.json`
is the closest thing to a real example of the extracted-record shape.

## The 3-way split

| Person | Owns | Why this grouping |
|---|---|---|
| **Person 1** | AWS/Bedrock setup (Step 0) + Extraction Agent + Knowledge base (DynamoDB/S3 schema) | Foundation work everyone else depends on. Gets it done first, then has bandwidth to help debug wherever's stuck later. |
| **Person 2** | Trend Detection Agent + Advice Agent | The differentiator lives here — pair these two together since Advice directly consumes Trend Flag output. Highest-stakes, most-judged piece, so it deserves one dedicated owner rather than being split further. |
| **Person 3** | Reply Drafting Agent + LangGraph Orchestration + Telegram bot interface | The "glue" role — ties the whole pipeline together and owns the most visible demo surface (the bot). Reply Drafting is intentionally the lightest agent, freeing time for orchestration + bot work. |

**Why not "one agent each, 4 agents 3 people":** Trend Detection and Advice are
tightly coupled (Advice literally consumes Trend Flag records) — splitting
them across two people means constant handoff friction on the most important
feature. Better to have one person own that chain end-to-end.

## Day-by-day

**Day 1**
- P1: AWS setup for the whole team (unblocks everyone), then start Extraction Agent
- P2: Design the Trend Detection counting logic + acceleration rule in plain Python (no AWS needed yet — can start immediately)
- P3: Stand up the Telegram bot skeleton against mocked JSON matching SCHEMA.md, so it renders a fake weekly brief before any real agent exists

**Day 2**
- P1: Finish Extraction Agent, wire to DynamoDB, hand off sample extracted records to P2
- P2: Wire Trend Detection to real extracted records, start Advice Agent (few-shot prompt with good/bad examples)
- P3: Build LangGraph orchestration skeleton with stub nodes, start Reply Drafting Agent

**Day 3**
- P1: Free to help debug wherever's behind, start on multi-language/translation edge cases
- P2: Advice Agent actionability testing — get real numbers against your ~20 synthetic reviews
- P3: Connect real agent outputs into the Telegram bot, replace mocked data

**Day 4**
- Everyone: integration testing end-to-end, demo video recording, deck assembly

**One thing to lock before splitting:** Person 1 needs to finalize the
DynamoDB record shape (as `SCHEMA.md`) by end of Day 1 — Persons 2 and 3 are
both reading/writing against it, so if that contract shifts mid-week it
breaks both of their work simultaneously. Worth a 15-minute sync before
everyone scatters.

---

## Step 0 — One-time AWS setup (whole team)

> **This section now matches `SETUP.md` exactly.** Two earlier drafts of this
> plan are superseded by what's below: one described a `workshop` SSO profile
> in `ap-southeast-1` before that was confirmed as the actual setup, and a
> later one described logging in through an IAM Identity Center portal with a
> `hackathon` profile in `us-east-1` — that flow does not match how this
> hackathon's account is provisioned. `SETUP.md` is the source of truth; this
> is the condensed version.

1. Run `aws configure sso` once per teammate — SSO start URL from the
   hackathon training deck, SSO region `ap-southeast-1`, region
   `ap-southeast-1`, profile name `workshop`.
2. `aws sso login --profile workshop`, then verify with
   `aws sts get-caller-identity --profile workshop` (must print an
   account/ARN, not an error).
3. `.env`:
   ```
   LLM_PROVIDER=bedrock
   AWS_PROFILE=workshop
   AWS_DEFAULT_REGION=ap-southeast-1
   BEDROCK_MODEL_EXTRACTION=anthropic.claude-3-haiku-20240307-v1:0
   BEDROCK_MODEL_REASONING=anthropic.claude-3-5-sonnet-20240620-v1:0
   ```

**Why these specific model ids:** this AWS org has a Service Control Policy
that restricts Bedrock to `ap-southeast-1` only. Claude Haiku 4.5 / Sonnet 4.5
exist here only as cross-region inference profiles (`us.*`/`global.*`/
`apac.*`), which the SCP denies regardless of the region set in `.env` — so
don't reach for those ids. The on-demand ids above are confirmed working
directly in `ap-southeast-1` and are what every agent in this repo uses.

If you ever change these, re-verify with a raw CLI call first (see
`SETUP.md` §3) — it's faster to debug than through the app. AWS SSO sessions
also expire (check with `aws sts get-caller-identity --profile workshop`
before a demo) — re-run `aws sso login --profile workshop` if it's stale.

**Cost discipline** (real budget: $20 hard cap, team-wide, does not reset):
avoid OpenSearch, SageMaker real-time endpoints, NAT Gateways, load
balancers, always-on EC2/RDS, and Bedrock Provisioned Throughput. Stick to
Bedrock on-demand, Lambda, DynamoDB on-demand, and S3.

---

## Agent 1 — Extraction Agent (Track A, Person 1)

**What it does:** raw review text → structured JSON (topic, sentiment,
entities, language).

**Model:** Claude Haiku 4.5 — high-volume, low-reasoning work, use the cheap
model.

**Steps:**
1. Define the output shape as a Pydantic model matching `SCHEMA.md`'s
   Extracted Review Record (topic from the controlled vocabulary, sentiment,
   entity mentions, detected language).
2. System prompt: instruct the model to extract those exact fields and
   nothing else — single call, no tools, no loop.
3. Translation: if the review isn't English, translate the extracted text
   fields to English before returning them, but keep the original language
   tagged in a `language` field.
4. `temperature=0` — you want consistent, repeatable extraction, not
   creativity.
5. Validate the JSON response against the Pydantic schema before writing to
   DynamoDB. If it fails to parse, log it — don't silently drop it.

Not a "loop" agent — one call in, one structured object out.

---

## Agent 2 — Trend Detection Agent (Track B, Person 2)

**What it does:** looks at extracted records grouped by week, applies the
acceleration rule (3+ weeks increasing, min 2 mentions latest week), outputs
Trend Flag records.

**Model:** Haiku is enough — closer to a counting task than a reasoning
task, so most of the logic is plain Python, not the LLM.

**Steps:**
1. Counting logic in code, not in the prompt: group extracted records by
   topic + ISO week, count mentions per week.
2. Apply the rule in Python (strictly increasing across 3+ weeks, ≥2
   mentions latest week) — deterministic and cheap, not left to the LLM to
   "decide."
3. Only call the LLM once you have a candidate trend — ask it to write a
   one-sentence, human-readable summary of the trend (e.g. "Complaints about
   wait time have risen for 3 consecutive weeks") using the counts as input.
   Small, cheap call.
4. Output a Trend Flag record matching `SCHEMA.md`, including the actual
   review quotes/dates behind it (pulled from the extracted records
   directly — don't ask the LLM to invent them).

Mostly deterministic code with one small LLM call at the end for the
human-readable framing.

---

## Agent 3 — Advice Agent (Track B, Person 2)

**What it does:** takes a Trend Flag, produces one specific, actionable fix.

**Model:** Sonnet — this is the reasoning step where "staff the 12:00–13:30
slot" vs. "improve service" is the whole differentiator, worth the extra
cost here.

**Steps:**
1. System prompt with 2–3 few-shot examples of good vs. bad advice — this is
   exactly a case where few-shot beats zero-shot, because "specific and
   actionable" is a formatting convention, not something a description alone
   reliably produces.
2. Input: the Trend Flag (topic, weeks, mention counts, sample review quotes
   with timestamps).
3. Output: one sentence of advice, plus a boolean/score checked in code
   afterward — does it contain a specific time, staff role, or menu item? If
   not, it fails the actionability bar and should be flagged, not shipped.

Single most important agent for the pitch — spend the best debugging time
here.

---

## Agent 4 — Reply Drafting Agent (Track C, Person 3)

**What it does:** drafts a customer-facing reply to a single review.

**Model:** Haiku — commoditized, low-stakes, keep it cheap.

**Steps:**
1. Simple single-call agent: review text + sentiment → drafted reply in the
   review's original language (or English).
2. Build this last, after Tracks A and B are stable — least differentiated
   part of the system.

---

## Orchestration — LangGraph (Person 3)

1. Define a LangGraph `StateGraph` where each node is one of the agents
   above. State carries the review through: raw → extracted → (batched
   weekly) → trend flags → advice → (parallel) → reply draft.
2. Use `create_react_agent` only where an agent actually needs to
   reason/loop (arguably none of these do — each is a single-shot call, so
   plain function nodes in the graph are simpler and cheaper than full ReAct
   agents).
3. Deploy via Bedrock AgentCore's `@app.entrypoint` handler, tested locally
   first with `POST` to `localhost:8080` before touching actual deployment.
4. Bound everything with a hard iteration cap in state — even though the
   pipeline is mostly linear, cap any retry logic (e.g. re-attempting a
   failed extraction).

---

## Interface — Telegram bot (Person 3)

1. Build against mocked JSON matching `SCHEMA.md` records first (Day 1), so
   it's not blocked waiting for the agents to be finished. Starter version:
   `person3_telegram_brief/telegram_brief.py`
   (`format_brief()`) + `send_telegram.py` — already built and verified
   sending to a real Telegram chat via the bot API.
2. Telegram bot reads Trend Flags + Advice + Reply Drafts from DynamoDB,
   formats the Monday message (what got worse, one fix, what's working,
   draft replies with inline tap-approve buttons).
3. Wire tap-approve/reject to write back a small feedback log — the answer
   to the "not as accurate as humans" concern, even if minimal.