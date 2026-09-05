# SETUP.md — Step 0 (AWS/Bedrock) + local dev

Person 1 owns this. The whole team runs the **AWS SSO** part once on their own machine.

## 1. Prerequisites (already done on Person 1's machine)

- AWS CLI v2 — `aws --version` must print `aws-cli/2.x`
  (installed here via `brew install awscli`)
- `uv` for the Python env — `uv --version`
- Python 3.11+

## 2. AWS SSO — every teammate runs this once

```bash
aws configure sso
#   SSO start URL:      <from the hackathon training deck>
#   SSO region:         ap-southeast-1
#   region:             ap-southeast-1
#   profile name:       workshop

aws sso login --profile workshop
aws sts get-caller-identity --profile workshop   # must print an account/ARN, not an error
```

If `aws sts get-caller-identity` fails, nothing else in this repo that touches
Bedrock or DynamoDB will work. Fix this first.

## 3. Model access — read this before touching the console

**This account does NOT need the Bedrock → Model access console page.** We
verified directly: this hackathon's AWS org has a **Service Control Policy that
restricts Bedrock to the `ap-southeast-1` region**. Claude Haiku 4.5 and Sonnet
4.5 only exist here as *cross-region inference profiles*
(`global.anthropic.claude-haiku-4-5-...`, `apac.anthropic...`), which by
definition can route through other regions — so the SCP denies them with
`AccessDeniedException ... explicit deny in a service control policy`, no matter
what the console's model-access toggle says. This is an org-level guardrail, not
a per-user permission — there is nothing to grant yourself.

What **does** work: calling an older Claude model **directly** (no inference
profile) with `--region ap-southeast-1`. Confirmed live against this account:

| use case | model id | tier |
|---|---|---|
| extraction (cheap, high volume) | `anthropic.claude-3-haiku-20240307-v1:0` | Haiku 3 |
| advice / reasoning | `anthropic.claude-3-5-sonnet-20240620-v1:0` | Sonnet 3.5 |

These are already the defaults in `.env` / `config.py`. If you ever change
`BEDROCK_MODEL_*`, re-verify with a raw CLI call first — it's much faster to
debug than through the app:

```bash
cat > /tmp/body.json <<'EOF'
{"anthropic_version":"bedrock-2023-05-31","max_tokens":50,
 "messages":[{"role":"user","content":[{"type":"text","text":"say hi"}]}]}
EOF
aws bedrock-runtime invoke-model \
  --profile workshop --region ap-southeast-1 \
  --model-id "anthropic.claude-3-haiku-20240307-v1:0" \
  --cli-binary-format raw-in-base64-out \
  --body file:///tmp/body.json /tmp/out.json && cat /tmp/out.json
```

If you get `ValidationException ... on-demand throughput isn't supported`, that
model needs an inference profile in this region — check
`aws bedrock list-inference-profiles --profile workshop --region ap-southeast-1`
for an `apac.*` or `global.*` variant, but expect the SCP to block it anyway
unless it's scoped purely to `ap-southeast-1`.

Quick check once granted:

```bash
aws bedrock list-foundation-models --profile workshop --region ap-southeast-1 \
  --query "modelSummaries[?contains(modelId, 'claude-haiku-4-5')].modelId"
```

## 4. Python env

```bash
cd simplifynext
uv sync                       # creates .venv from pyproject.toml
cp .env.example .env          # then edit .env
```

`.env` knobs:

| var | values | meaning |
|---|---|---|
| `LLM_PROVIDER` | `mock` \| `bedrock` | `mock` = offline heuristic, no AWS, no cost. `bedrock` = real Claude. |
| `STORAGE_BACKEND` | `local` \| `dynamodb` | `local` = `data/store/*.json`. `dynamodb` = real tables. |

Teammates who just need data to build against: leave both on `mock` / `local`.

## 5. Run the Extraction Agent

```bash
# offline smoke test (no AWS needed)
uv run simplifynext extract --input data/synthetic_reviews.json
uv run simplifynext show --business sg-hawker-042

# one review, real Bedrock, don't store
#   (needs LLM_PROVIDER=bedrock + step 2 + step 3)
uv run simplifynext extract --text "等了45分钟，服务员态度很差" --date 2026-08-30 --dry-run

uv run pytest        # offline test suite
```

## 6. (Optional) provision real AWS storage

Only if you want `STORAGE_BACKEND=dynamodb`. Costs cents on `PAY_PER_REQUEST`.

```bash
aws sso login --profile workshop
./scripts/provision_aws.sh            # create tables + bucket
./scripts/provision_aws.sh teardown  # remove them after the demo
```

## 7. Hand-off to Person 2 / Person 3

- **Contract:** `SCHEMA.md` (locked). Models: `src/simplifynext/models.py`.
- **Read/write data only through** `simplifynext.repository.get_repository()` —
  never touch the JSON files or DynamoDB directly, so the backend stays swappable.
- Person 2 pulls extracted records with
  `get_repository().list_extracted(business_id=..., topic="wait_time")`.
- The seed data in `data/synthetic_reviews.json` contains a deliberate
  accelerating `wait_time` trend (W33=2 → W34=3 → W35=5 negative mentions) for
  Trend Detection to catch, plus noise (cleanliness, price, food quality, praise).
