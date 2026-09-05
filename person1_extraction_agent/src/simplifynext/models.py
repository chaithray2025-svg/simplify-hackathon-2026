"""Pydantic models — the runtime form of SCHEMA.md.

Person 2 / Person 3: import these, don't redefine the shapes. If a field needs to
change, change it here + SCHEMA.md + announce it.
"""

from __future__ import annotations

import datetime as _dt
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .topics import ENTITY_KINDS, LANGUAGES, SENTIMENTS, TIME_SLOTS, TOPICS

Sentiment = Literal["positive", "neutral", "negative", "mixed"]
Language = Literal["en", "zh", "ta", "ms", "other"]


def iso_week_of(date_str: str) -> str:
    """'2026-08-30' -> '2026-W35' (ISO year + ISO week)."""
    d = _dt.date.fromisoformat(date_str)
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


# --------------------------------------------------------------------------- #
# §1 RawReview                                                                #
# --------------------------------------------------------------------------- #
class RawReview(BaseModel):
    review_id: str
    business_id: str
    source: Literal["google", "facebook", "tripadvisor", "manual", "seed"] = "seed"
    review_date: str  # YYYY-MM-DD
    ingested_at: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    author_name: Optional[str] = None
    text: str
    s3_key: Optional[str] = None

    @field_validator("review_date")
    @classmethod
    def _valid_date(cls, v: str) -> str:
        _dt.date.fromisoformat(v)  # raises if malformed
        return v

    @field_validator("text")
    @classmethod
    def _nonempty_text(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("RawReview.text must not be empty")
        return v


# --------------------------------------------------------------------------- #
# §2 ExtractedReviewRecord                                                    #
# --------------------------------------------------------------------------- #
class EntityMention(BaseModel):
    kind: Literal[
        "menu_item", "staff_role", "staff_name", "location_area",
        "time_slot", "wait_time", "price", "competitor", "other",
    ]
    value: str
    sentiment: Sentiment

    @field_validator("value")
    @classmethod
    def _trim(cls, v: str) -> str:
        return v.strip()


class ExtractedReviewRecord(BaseModel):
    review_id: str
    business_id: str
    review_date: str
    iso_week: str = ""
    extracted_at: Optional[str] = None
    model_id: str = ""
    schema_version: int = 1

    language: Language
    is_translated: bool
    text_en: str
    text_original: str

    sentiment: Sentiment
    rating: Optional[int] = Field(default=None, ge=1, le=5)

    topic: str
    secondary_topics: list[str] = Field(default_factory=list)

    entities: list[EntityMention] = Field(default_factory=list)
    time_slot: Literal[
        "breakfast", "lunch", "tea", "dinner", "late_night", "unknown"
    ] = "unknown"
    actionable_quote: str = ""
    confidence: float = Field(ge=0.0, le=1.0)

    # ---- validators (SCHEMA.md §2 rules) ---- #
    @field_validator("topic")
    @classmethod
    def _topic_in_vocab(cls, v: str) -> str:
        if v not in TOPICS:
            raise ValueError(f"topic {v!r} not in controlled vocabulary")
        return v

    @field_validator("entities")
    @classmethod
    def _max_entities(cls, v: list[EntityMention]) -> list[EntityMention]:
        if len(v) > 8:
            raise ValueError("max 8 entities")
        return v

    @model_validator(mode="after")
    def _cross_field(self) -> "ExtractedReviewRecord":
        # rule 2: secondary_topics ⊆ vocab, deduped, primary removed, <=3
        seen: list[str] = []
        for t in self.secondary_topics:
            if t not in TOPICS:
                raise ValueError(f"secondary topic {t!r} not in controlled vocabulary")
            if t != self.topic and t not in seen:
                seen.append(t)
        object.__setattr__(self, "secondary_topics", seen[:3])

        # rule 4: translation flag consistency
        if self.language == "en" and self.is_translated:
            raise ValueError("is_translated must be False when language == 'en'")
        if self.language not in ("en", "other") and not self.is_translated:
            raise ValueError("is_translated must be True for non-English reviews")

        # rule 5: text_en present; identity for English
        if not self.text_en.strip():
            raise ValueError("text_en must not be empty")
        if self.language == "en" and self.text_en.strip() != self.text_original.strip():
            object.__setattr__(self, "text_en", self.text_original)

        # derive iso_week if not supplied
        if not self.iso_week:
            object.__setattr__(self, "iso_week", iso_week_of(self.review_date))

        return self

    # DynamoDB helpers (real backend) -------------------------------------- #
    def ddb_keys(self) -> dict[str, str]:
        return {
            "PK": self.business_id,
            "SK": f"EXT#{self.review_id}",
            "GSI1PK": f"{self.business_id}#{self.topic}",
            "GSI1SK": self.review_date,
        }


# --------------------------------------------------------------------------- #
# §3 TrendFlag  (Person 2 writes; defined here so everyone shares the shape)  #
# --------------------------------------------------------------------------- #
class TrendEvidence(BaseModel):
    review_id: str
    review_date: str
    quote: str
    language: Language


class TrendFlag(BaseModel):
    trend_id: str
    business_id: str
    detected_at: Optional[str] = None
    detected_week: str
    topic: str
    window_weeks: list[str]
    weekly_counts: list[int]
    direction: Literal["worsening", "improving", "flat"]
    severity: float = Field(ge=0.0, le=1.0)
    summary: str
    evidence: list[TrendEvidence] = Field(default_factory=list)
    status: Literal["open", "advised", "resolved", "dismissed"] = "open"

    @model_validator(mode="after")
    def _aligned(self) -> "TrendFlag":
        if len(self.window_weeks) != len(self.weekly_counts):
            raise ValueError("window_weeks and weekly_counts must be the same length")
        if self.topic not in TOPICS:
            raise ValueError(f"topic {self.topic!r} not in controlled vocabulary")
        return self


# --------------------------------------------------------------------------- #
# §4 AdviceRecord  (Person 2)                                                 #
# --------------------------------------------------------------------------- #
class Actionability(BaseModel):
    has_time_or_daypart: bool = False
    has_staff_role_or_headcount: bool = False
    has_menu_item: bool = False
    passes_bar: bool = False

    @model_validator(mode="after")
    def _bar(self) -> "Actionability":
        object.__setattr__(
            self,
            "passes_bar",
            self.has_time_or_daypart
            or self.has_staff_role_or_headcount
            or self.has_menu_item,
        )
        return self


class AdviceRecord(BaseModel):
    advice_id: str
    trend_id: str
    business_id: str
    created_at: Optional[str] = None
    model_id: str = ""
    topic: str
    advice: str
    rationale: str = ""
    actionability: Actionability = Field(default_factory=Actionability)
    expected_metric: str = ""
    baseline_value: Optional[float] = None
    target_value: Optional[float] = None
    review_after_week: str = ""
    status: Literal["proposed", "sent", "accepted", "rejected", "verified"] = "proposed"


# --------------------------------------------------------------------------- #
# §5 ReplyDraft  (Person 3)                                                   #
# --------------------------------------------------------------------------- #
class ReplyDraft(BaseModel):
    reply_id: str
    review_id: str
    business_id: str
    created_at: Optional[str] = None
    model_id: str = ""
    reply_language: Language
    reply_text: str
    reply_text_en: str
    tone: Literal["apologetic", "grateful", "neutral", "corrective"] = "neutral"
    references_fix: bool = False
    status: Literal["draft", "approved", "edited", "rejected", "posted"] = "draft"


# --------------------------------------------------------------------------- #
# §6 FeedbackLog  (Person 3)                                                  #
# --------------------------------------------------------------------------- #
class FeedbackLog(BaseModel):
    feedback_id: str
    business_id: str
    created_at: Optional[str] = None
    actor: Literal["owner", "system"] = "owner"
    target_type: Literal["reply_draft", "advice", "trend_flag"]
    target_id: str
    action: Literal["approved", "rejected", "edited", "snoozed"]
    edited_text: Optional[str] = None
    note: Optional[str] = None
    brief_id: str = ""


# Exposed enums for prompt building / tests.
__all__ = [
    "RawReview",
    "EntityMention",
    "ExtractedReviewRecord",
    "TrendEvidence",
    "TrendFlag",
    "Actionability",
    "AdviceRecord",
    "ReplyDraft",
    "FeedbackLog",
    "iso_week_of",
    "SENTIMENTS",
    "LANGUAGES",
    "TOPICS",
    "ENTITY_KINDS",
    "TIME_SLOTS",
]
