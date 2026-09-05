"""Thin Bedrock wrapper: one InvokeModel call in, text out.

`LLM_PROVIDER=bedrock` -> real boto3 call against Claude on Bedrock.
`LLM_PROVIDER=mock`    -> deterministic heuristic response, no AWS, no cost.
                         Lets Person 2/3 run the whole pipeline offline.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .config import SETTINGS


class LLMError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# Real Bedrock                                                                #
# --------------------------------------------------------------------------- #
_runtime = None


def _client():
    global _runtime
    if _runtime is None:
        import boto3  # imported lazily so `mock` mode needs no AWS deps configured

        session = boto3.Session(
            profile_name=SETTINGS.aws_profile, region_name=SETTINGS.aws_region
        )
        _runtime = session.client("bedrock-runtime")
    return _runtime


def _invoke_bedrock(
    *,
    model_id: str,
    system: str,
    user: str,
    temperature: float,
    max_tokens: int,
) -> str:
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": [{"type": "text", "text": user}]}],
    }
    try:
        resp = _client().invoke_model(modelId=model_id, body=json.dumps(body))
        payload = json.loads(resp["body"].read())
    except Exception as exc:  # noqa: BLE001 - surface any boto/credential error uniformly
        raise LLMError(f"Bedrock invoke_model failed: {exc}") from exc

    try:
        return "".join(
            block.get("text", "")
            for block in payload["content"]
            if block.get("type") == "text"
        )
    except (KeyError, TypeError) as exc:
        raise LLMError(f"Unexpected Bedrock response shape: {payload!r}") from exc


# --------------------------------------------------------------------------- #
# Mock                                                                        #
# --------------------------------------------------------------------------- #
_MOCK_TOPIC_HINTS = [
    ("wait_time", ["wait", "waited", "queue", "slow", "45 min", "took forever",
                    "等", "排队", "காத்த", "menunggu", "lambat"]),
    ("food_temperature", ["cold", "lukewarm", "not hot", "冷", "குளிர்", "sejuk"]),
    ("food_quality", ["bland", "stale", "overcooked", "undercooked", "tasteless",
                       "delicious", "tasty", "好吃", "难吃", "sedap", "ருசி"]),
    ("staff_friendliness", ["rude", "friendly", "attitude", "polite", "态度",
                             "பணிவ", "biadap", "mesra"]),
    ("order_accuracy", ["wrong order", "missing", "wrong item", "gave me the wrong",
                         "点错", "salah pesanan"]),
    ("cleanliness", ["dirty", "sticky", "unclean", "filthy", "脏", "kotor",
                      "அசுத்த"]),
    ("price_value", ["expensive", "overpriced", "pricey", "worth", "贵", "mahal"]),
    ("portion_size", ["portion", "small serving", "tiny", "份量", "sikit"]),
]


def _mock_extract_json(user_prompt: str) -> str:
    """Very rough heuristic extraction so the offline pipeline produces valid records.

    NOTE: the mock is a convenience for running the plumbing without AWS. It is NOT
    accurate — for correct offline data (e.g. Person 2's trend work) load
    data/extracted_reviews.golden.json via `simplifynext seed`.
    """
    # The real review text sits between the triple-quote fences in the user prompt.
    m = re.search(r'"""\s*(.*?)\s*"""', user_prompt, flags=re.DOTALL)
    user_review = m.group(1).strip() if m else user_prompt
    text = user_review.lower()

    lang = "en"
    if re.search(r"[一-鿿]", user_review):
        lang = "zh"
    elif re.search(r"[஀-௿]", user_review):
        lang = "ta"
    elif re.search(r"\b(sedap|tak|makanan|lambat|kotor|mahal|menunggu|pelayan)\b", text):
        lang = "ms"

    topic = "other"
    for cand, hints in _MOCK_TOPIC_HINTS:
        if any(h.lower() in text for h in hints):
            topic = cand
            break

    negatives = ["rude", "cold", "dirty", "slow", "wrong", "bad", "worst", "expensive",
                 "waited", "queue", "难吃", "脏", "贵", "lambat", "kotor", "biadap"]
    positives = ["great", "delicious", "friendly", "love", "best", "amazing", "好吃",
                 "sedap", "mesra", "excellent"]
    neg = any(w in text for w in negatives)
    pos = any(w in text for w in positives)
    sentiment = "mixed" if neg and pos else "negative" if neg else "positive" if pos else "neutral"

    slot = "unknown"
    for s, hints in [
        ("lunch", ["lunch", "noon", "12", "1pm", "午"]),
        ("dinner", ["dinner", "evening", "7pm", "8pm", "晚"]),
        ("breakfast", ["breakfast", "morning", "kaya toast", "早"]),
    ]:
        if any(h in text for h in hints):
            slot = s
            break

    text_en = user_review if lang == "en" else f"[mock-translation] {user_review}"
    record = {
        "language": lang,
        "is_translated": lang not in ("en", "other"),
        "text_en": text_en,
        "sentiment": sentiment,
        "topic": topic,
        "secondary_topics": [],
        "entities": [],
        "time_slot": slot,
        "actionable_quote": user_review.split(".")[0][:160] if lang == "en"
        else f"[mock] {user_review[:120]}",
        "confidence": 0.4,
    }
    return json.dumps(record, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Public entry point                                                          #
# --------------------------------------------------------------------------- #
def complete(
    *,
    model_id: str,
    system: str,
    user: str,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    _mock_kind: str = "extract",
) -> str:
    """Return raw model text. Caller parses/validates."""
    if SETTINGS.llm_provider == "mock":
        if _mock_kind == "extract":
            return _mock_extract_json(user)
        return "[mock] " + user[:200]
    if SETTINGS.llm_provider == "bedrock":
        return _invoke_bedrock(
            model_id=model_id,
            system=system,
            user=user,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    raise LLMError(f"Unknown LLM_PROVIDER={SETTINGS.llm_provider!r} (want 'bedrock' or 'mock')")


def extract_json_block(raw: str) -> dict[str, Any]:
    """Pull the first well-formed JSON object out of a model response."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not m:
        raise LLMError(f"No JSON object found in model output: {raw[:200]!r}")
    return json.loads(m.group(0))
