"""Offline tests for Person 1's deliverables. Run: `uv run pytest`.

These use LLM_PROVIDER=mock (set in conftest) so they need no AWS.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simplifynext.extraction_agent import extract, run_batch
from simplifynext.models import ExtractedReviewRecord, RawReview, iso_week_of
from simplifynext.repository import LocalJSONRepository
from simplifynext.topics import LANGUAGES, SENTIMENTS, TOPICS

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATA = DATA_DIR / "synthetic_reviews.json"
GOLDEN = DATA_DIR / "extracted_reviews.golden.json"


def _raws() -> list[RawReview]:
    return [RawReview(**r) for r in json.loads(DATA.read_text("utf-8"))]


def _golden() -> list[ExtractedReviewRecord]:
    return [ExtractedReviewRecord(**r) for r in json.loads(GOLDEN.read_text("utf-8"))]


def test_iso_week():
    assert iso_week_of("2026-08-11") == "2026-W33"
    assert iso_week_of("2026-08-24") == "2026-W35"


def test_every_seed_review_extracts_to_valid_record():
    for raw in _raws():
        res = extract(raw)
        assert res.ok, f"{raw.review_id}: {res.error}"
        rec = res.record
        assert isinstance(rec, ExtractedReviewRecord)
        assert rec.topic in TOPICS
        assert rec.sentiment in SENTIMENTS
        assert rec.language in LANGUAGES
        assert rec.text_en.strip()
        assert rec.review_id == raw.review_id
        assert rec.iso_week == iso_week_of(raw.review_date)
        assert rec.topic not in rec.secondary_topics


def test_non_english_is_flagged_translated():
    by_id = {r.review_id: r for r in _raws()}
    res = extract(by_id["seed-002"])  # Chinese
    assert res.ok
    assert res.record.language == "zh"
    assert res.record.is_translated is True
    assert res.record.text_original == by_id["seed-002"].text


def test_english_is_not_translated():
    by_id = {r.review_id: r for r in _raws()}
    res = extract(by_id["seed-001"])
    assert res.ok
    assert res.record.language == "en"
    assert res.record.is_translated is False
    assert res.record.text_en == res.record.text_original


def test_is_translated_is_derived_not_trusted_from_model(monkeypatch):
    """Regression: a live Bedrock call once translated a Malay review correctly
    but self-reported is_translated=false. That field must be derived from
    `language` in code, never taken from the model's JSON as-is."""
    import simplifynext.extraction_agent as ea

    def fake_complete(**kwargs):
        return (
            '{"language": "ms", "is_translated": false, '
            '"text_en": "translated text", "sentiment": "negative", '
            '"topic": "cleanliness", "confidence": 0.9}'
        )

    monkeypatch.setattr(ea, "complete", fake_complete)
    raw = RawReview(
        review_id="r1", business_id="b1", review_date="2026-08-15",
        text="teks asal dalam bahasa Melayu",
    )
    res = ea.extract(raw)
    assert res.ok, res.error
    assert res.record.language == "ms"
    assert res.record.is_translated is True


def test_low_signal_review_forces_topic_other(monkeypatch):
    """Regression: live Bedrock call on '🔥🔥🔥' returned topic=ambience_noise,
    confidence=0.8 — fabricated signal from an emoji-only review. Word count is
    checked in code and overrides the model's topic/confidence claim."""
    import simplifynext.extraction_agent as ea

    def fake_complete(**kwargs):
        return (
            '{"language": "other", "is_translated": false, "text_en": "🔥🔥🔥", '
            '"sentiment": "positive", "topic": "ambience_noise", "confidence": 0.8}'
        )

    monkeypatch.setattr(ea, "complete", fake_complete)
    raw = RawReview(review_id="r2", business_id="b1", review_date="2026-08-22", text="🔥🔥🔥")
    res = ea.extract(raw)
    assert res.ok, res.error
    assert res.record.topic == "other"
    assert res.record.secondary_topics == []
    assert res.record.confidence <= 0.3


def test_invalid_topic_is_rejected_not_stored(tmp_path):
    repo = LocalJSONRepository(store_dir=tmp_path)
    bad = {
        "review_id": "x1", "business_id": "b1", "review_date": "2026-08-11",
        "language": "en", "is_translated": False,
        "text_en": "hi", "text_original": "hi",
        "sentiment": "negative", "topic": "not_a_real_topic",
        "confidence": 0.5,
    }
    with pytest.raises(Exception):
        ExtractedReviewRecord(**bad)


def test_run_batch_writes_store(tmp_path):
    repo = LocalJSONRepository(store_dir=tmp_path)
    stats = run_batch(_raws(), repo=repo)
    assert stats["error"] == 0
    assert stats["ok"] == stats["total"] == 22
    stored = repo.list_extracted(business_id="sg-hawker-042")
    assert len(stored) == 22


def test_golden_file_matches_every_seed_review():
    raw_ids = {r.review_id for r in _raws()}
    golden = _golden()
    assert {g.review_id for g in golden} == raw_ids
    for g in golden:
        assert g.topic in TOPICS
        assert g.language in LANGUAGES
        assert g.is_translated == (g.language not in ("en", "other"))


def test_wait_time_trend_is_present_for_person2(tmp_path):
    """The hand-verified golden data must contain the accelerating wait_time trend
    Person 2's Trend Detection Agent is supposed to catch:
    negative mentions 2 -> 3 -> 5 across W33, W34, W35."""
    repo = LocalJSONRepository(store_dir=tmp_path)
    for g in _golden():
        repo.put_extracted(g)
    wt = repo.list_extracted(topic="wait_time")
    counts: dict[str, int] = {}
    for r in wt:
        if r.sentiment in ("negative", "mixed"):
            counts[r.iso_week] = counts.get(r.iso_week, 0) + 1
    assert counts.get("2026-W33", 0) == 2
    assert counts.get("2026-W34", 0) == 3
    assert counts.get("2026-W35", 0) == 5
    assert counts["2026-W33"] < counts["2026-W34"] < counts["2026-W35"]
