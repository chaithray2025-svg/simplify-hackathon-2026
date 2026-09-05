"""Agent 1 — Extraction Agent (Track A).

raw review text  ->  one validated ExtractedReviewRecord

- Model: Claude Haiku 4.5 on Bedrock (high volume, low reasoning).
- One InvokeModel call. No tools, no loop.
- temperature = 0 (repeatable extraction, not creativity).
- Non-English reviews are translated to English; original language is tagged.
- Output is validated against the Pydantic schema before it is stored.
  Parse/validation failure -> logged via repo.log_extraction_error, never dropped.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from dataclasses import dataclass

from pydantic import ValidationError

from . import SCHEMA_VERSION
from .bedrock_client import complete, extract_json_block
from .config import SETTINGS
from .models import ExtractedReviewRecord, RawReview, iso_week_of
from .repository import Repository, get_repository
from .topics import ENTITY_KINDS, LANGUAGES, TIME_SLOTS, TOPIC_GLOSS, TOPICS

_TOPIC_LINES = "\n".join(f"  - {t}: {TOPIC_GLOSS[t]}" for t in TOPICS)

SYSTEM_PROMPT = f"""\
You are an extraction engine for a Singapore F&B review tool. You read ONE customer
review and return ONE JSON object. You never chat, explain, or add commentary.

Extract EXACTLY these fields and nothing else:

- language: the review's original language. One of: {", ".join(LANGUAGES)}.
    Use "zh" for any Chinese, "ta" for Tamil, "ms" for Malay, "en" for English,
    "other" for anything else.
- is_translated: true if you translated the text fields below into English,
    false only when language == "en".
- text_en: the full review translated into natural English. If language == "en",
    copy the review verbatim.
- sentiment: overall sentiment. One of: positive, neutral, negative, mixed.
- topic: the SINGLE most important operational topic, chosen ONLY from this list:
{_TOPIC_LINES}
- secondary_topics: 0 to 3 more topics from the SAME list (exclude the primary
    topic). Use [] if none clearly apply.
- entities: concrete things the review names. Each is
    {{"kind": <one of {", ".join(ENTITY_KINDS)}>, "value": <short English span>,
      "sentiment": <positive|neutral|negative|mixed>}}.
    Examples: a dish ("laksa"), a staff role ("cashier"), a named staff member,
    a wait duration ("45 minutes"), a price ("$18"), an area ("outdoor seating").
    Max 8. Use [] if the review is vague.
- time_slot: the daypart the visit implies. One of: {", ".join(TIME_SLOTS)}.
    Use "unknown" if not stated or implied.
- actionable_quote: the single sentence from the review (in English) that a
    business owner would most need to act on. <= 200 characters.
- confidence: your confidence in this extraction, 0.0 to 1.0.

Rules:
- topic and secondary_topics MUST be exact strings from the list. Never invent a topic.
- Do not include the primary topic inside secondary_topics.
- Return ONLY the JSON object. No markdown fences, no prose.
"""

USER_TEMPLATE = """\
Review metadata:
- date: {review_date}
- star rating: {rating}
- source: {source}

Review text (original language, verbatim):
\"\"\"
{text}
\"\"\"

Return the JSON object now."""


@dataclass
class ExtractionResult:
    ok: bool
    record: ExtractedReviewRecord | None = None
    error: str | None = None
    raw_model_output: str | None = None


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_user_prompt(raw: RawReview) -> str:
    return USER_TEMPLATE.format(
        review_date=raw.review_date,
        rating="none" if raw.rating is None else raw.rating,
        source=raw.source,
        text=raw.text.strip(),
    )


def extract(raw: RawReview) -> ExtractionResult:
    """Run one extraction. Pure function — does not touch storage."""
    user_prompt = build_user_prompt(raw)
    try:
        raw_out = complete(
            model_id=SETTINGS.model_extraction,
            system=SYSTEM_PROMPT,
            user=user_prompt,
            temperature=0.0,
            max_tokens=900,
            _mock_kind="extract",
        )
    except Exception as exc:  # noqa: BLE001
        return ExtractionResult(ok=False, error=f"llm_call_failed: {exc}")

    try:
        payload = extract_json_block(raw_out)
    except Exception as exc:  # noqa: BLE001
        return ExtractionResult(ok=False, error=f"json_parse_failed: {exc}",
                                raw_model_output=raw_out)

    # Merge model output with the fields we own (not the model's job to set).
    payload = dict(payload)
    payload.setdefault("secondary_topics", [])
    payload.setdefault("entities", [])
    payload.setdefault("time_slot", "unknown")
    payload["review_id"] = raw.review_id
    payload["business_id"] = raw.business_id
    payload["review_date"] = raw.review_date
    payload["iso_week"] = iso_week_of(raw.review_date)
    payload["extracted_at"] = _now()
    payload["model_id"] = (
        "mock" if SETTINGS.llm_provider == "mock" else SETTINGS.model_extraction
    )
    payload["schema_version"] = SCHEMA_VERSION
    payload["text_original"] = raw.text
    payload["rating"] = raw.rating
    # is_translated is fully determined by language — don't trust the model's
    # self-report for it (observed live: it correctly translates a Malay review
    # but sometimes still reports is_translated=false). Derive it deterministically.
    lang = payload.get("language")
    if lang == "en":
        payload["is_translated"] = False
        payload.setdefault("text_en", raw.text)
    elif lang not in (None, "other"):
        payload["is_translated"] = True

    # Low-signal guard: emoji-only / near-empty reviews carry no real operational
    # content. Model still confidently picks a topic (observed live: "🔥🔥🔥" ->
    # ambience_noise, confidence 0.8). That's fabricated signal that would pollute
    # Trend Detection's counts. Word count is a fact, not a judgment call — enforce
    # in code, don't trust the model's confidence here.
    word_count = len(re.findall(r"\w+", raw.text, flags=re.UNICODE))
    if word_count < 3:
        payload["topic"] = "other"
        payload["secondary_topics"] = []
        payload["confidence"] = min(float(payload.get("confidence", 0.3)), 0.3)

    try:
        record = ExtractedReviewRecord(**payload)
    except ValidationError as exc:
        return ExtractionResult(
            ok=False,
            error="schema_validation_failed: "
            + "; ".join(f"{e['loc']}: {e['msg']}" for e in exc.errors()),
            raw_model_output=raw_out,
        )

    return ExtractionResult(ok=True, record=record, raw_model_output=raw_out)


def extract_and_store(raw: RawReview, repo: Repository | None = None) -> ExtractionResult:
    """Run extraction and persist. Failures are logged, not raised."""
    repo = repo or get_repository()
    repo.put_raw_review(raw)
    result = extract(raw)
    if result.ok and result.record is not None:
        repo.put_extracted(result.record)
    else:
        repo.log_extraction_error(
            {
                "review_id": raw.review_id,
                "business_id": raw.business_id,
                "text": raw.text,
                "raw_model_output": result.raw_model_output,
            },
            result.error or "unknown_error",
        )
    return result


def run_batch(raws: list[RawReview], repo: Repository | None = None) -> dict[str, int]:
    repo = repo or get_repository()
    ok = err = 0
    for raw in raws:
        res = extract_and_store(raw, repo)
        if res.ok:
            ok += 1
        else:
            err += 1
            print(f"  ! {raw.review_id}: {res.error}")
    return {"ok": ok, "error": err, "total": len(raws)}
