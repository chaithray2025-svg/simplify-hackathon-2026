"""Storage layer. Same API for the local JSON backend and real DynamoDB/S3.

    repo = get_repository()
    repo.put_raw_review(raw)
    repo.put_extracted(rec)
    repo.log_extraction_error(payload, "topic not in vocab")
    records = repo.list_extracted(business_id="sg-hawker-042")

Person 2/3: use `list_extracted` / `put_trend_flag` / `put_advice` / etc. Do not
read the JSON files or DynamoDB directly — go through here so the backend stays
swappable via STORAGE_BACKEND.
"""

from __future__ import annotations

import abc
import datetime as _dt
import json
import threading
from pathlib import Path
from typing import Any

from .config import SETTINGS, STORE_DIR
from .models import (
    AdviceRecord,
    ExtractedReviewRecord,
    FeedbackLog,
    RawReview,
    ReplyDraft,
    TrendFlag,
)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Repository(abc.ABC):
    # ---- raw + extracted (Person 1) ---- #
    @abc.abstractmethod
    def put_raw_review(self, raw: RawReview) -> None: ...

    @abc.abstractmethod
    def get_raw_review(self, review_id: str) -> RawReview | None: ...

    @abc.abstractmethod
    def list_raw_reviews(self, business_id: str | None = None) -> list[RawReview]: ...

    @abc.abstractmethod
    def put_extracted(self, rec: ExtractedReviewRecord) -> None: ...

    @abc.abstractmethod
    def list_extracted(
        self, business_id: str | None = None, topic: str | None = None
    ) -> list[ExtractedReviewRecord]: ...

    @abc.abstractmethod
    def log_extraction_error(self, payload: dict[str, Any], error: str) -> None: ...

    # ---- downstream records (Person 2 / 3) ---- #
    @abc.abstractmethod
    def put_trend_flag(self, flag: TrendFlag) -> None: ...

    @abc.abstractmethod
    def list_trend_flags(self, business_id: str | None = None) -> list[TrendFlag]: ...

    @abc.abstractmethod
    def put_advice(self, advice: AdviceRecord) -> None: ...

    @abc.abstractmethod
    def list_advice(self, business_id: str | None = None) -> list[AdviceRecord]: ...

    @abc.abstractmethod
    def put_reply_draft(self, draft: ReplyDraft) -> None: ...

    @abc.abstractmethod
    def list_reply_drafts(self, business_id: str | None = None) -> list[ReplyDraft]: ...

    @abc.abstractmethod
    def put_feedback(self, fb: FeedbackLog) -> None: ...

    @abc.abstractmethod
    def list_feedback(self, business_id: str | None = None) -> list[FeedbackLog]: ...


# --------------------------------------------------------------------------- #
# Local JSON backend                                                          #
# --------------------------------------------------------------------------- #
class LocalJSONRepository(Repository):
    """One JSON file per record type under data/store/. Good enough for a hackathon."""

    def __init__(self, store_dir: Path | None = None) -> None:
        self.dir = store_dir or STORE_DIR
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # file helpers -------------------------------------------------------- #
    def _path(self, name: str) -> Path:
        return self.dir / f"{name}.json"

    def _read(self, name: str) -> dict[str, Any]:
        p = self._path(name)
        if not p.exists():
            return {}
        return json.loads(p.read_text("utf-8") or "{}")

    def _write(self, name: str, data: dict[str, Any]) -> None:
        self._path(name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
        )

    def _upsert(self, name: str, key: str, model: Any) -> None:
        with self._lock:
            data = self._read(name)
            data[key] = model.model_dump(mode="json")
            self._write(name, data)

    def _all(self, name: str, model_cls: Any, business_id: str | None) -> list[Any]:
        rows = [model_cls(**v) for v in self._read(name).values()]
        if business_id is not None:
            rows = [r for r in rows if getattr(r, "business_id", None) == business_id]
        return rows

    # raw + extracted -------------------------------------------------------- #
    def put_raw_review(self, raw: RawReview) -> None:
        if raw.ingested_at is None:
            raw = raw.model_copy(update={"ingested_at": _now()})
        self._upsert("raw_reviews", raw.review_id, raw)

    def get_raw_review(self, review_id: str) -> RawReview | None:
        row = self._read("raw_reviews").get(review_id)
        return RawReview(**row) if row else None

    def list_raw_reviews(self, business_id: str | None = None) -> list[RawReview]:
        return self._all("raw_reviews", RawReview, business_id)

    def put_extracted(self, rec: ExtractedReviewRecord) -> None:
        if rec.extracted_at is None:
            rec = rec.model_copy(update={"extracted_at": _now()})
        self._upsert("extracted_reviews", rec.review_id, rec)

    def list_extracted(
        self, business_id: str | None = None, topic: str | None = None
    ) -> list[ExtractedReviewRecord]:
        rows = self._all("extracted_reviews", ExtractedReviewRecord, business_id)
        if topic is not None:
            rows = [r for r in rows if r.topic == topic or topic in r.secondary_topics]
        rows.sort(key=lambda r: r.review_date)
        return rows

    def log_extraction_error(self, payload: dict[str, Any], error: str) -> None:
        with self._lock:
            p = self._path("extraction_errors")
            log = json.loads(p.read_text("utf-8")) if p.exists() else []
            log.append({"logged_at": _now(), "error": error, "payload": payload})
            p.write_text(json.dumps(log, ensure_ascii=False, indent=2), "utf-8")

    # downstream ----------------------------------------------------------- #
    def put_trend_flag(self, flag: TrendFlag) -> None:
        if flag.detected_at is None:
            flag = flag.model_copy(update={"detected_at": _now()})
        self._upsert("trend_flags", flag.trend_id, flag)

    def list_trend_flags(self, business_id: str | None = None) -> list[TrendFlag]:
        return self._all("trend_flags", TrendFlag, business_id)

    def put_advice(self, advice: AdviceRecord) -> None:
        if advice.created_at is None:
            advice = advice.model_copy(update={"created_at": _now()})
        self._upsert("advice", advice.advice_id, advice)

    def list_advice(self, business_id: str | None = None) -> list[AdviceRecord]:
        return self._all("advice", AdviceRecord, business_id)

    def put_reply_draft(self, draft: ReplyDraft) -> None:
        if draft.created_at is None:
            draft = draft.model_copy(update={"created_at": _now()})
        self._upsert("reply_drafts", draft.reply_id, draft)

    def list_reply_drafts(self, business_id: str | None = None) -> list[ReplyDraft]:
        return self._all("reply_drafts", ReplyDraft, business_id)

    def put_feedback(self, fb: FeedbackLog) -> None:
        if fb.created_at is None:
            fb = fb.model_copy(update={"created_at": _now()})
        self._upsert("feedback", fb.feedback_id, fb)

    def list_feedback(self, business_id: str | None = None) -> list[FeedbackLog]:
        return self._all("feedback", FeedbackLog, business_id)


# --------------------------------------------------------------------------- #
# DynamoDB + S3 backend                                                       #
# --------------------------------------------------------------------------- #
class DynamoDBRepository(Repository):
    """Real AWS backend. Tables + bucket must exist (see scripts/provision_aws.sh)."""

    def __init__(self) -> None:
        import boto3

        sess = boto3.Session(
            profile_name=SETTINGS.aws_profile, region_name=SETTINGS.aws_region
        )
        self._ddb = sess.resource("dynamodb")
        self._s3 = sess.client("s3")
        self.t_reviews = self._ddb.Table(SETTINGS.ddb_table_reviews)
        self.t_trends = self._ddb.Table(SETTINGS.ddb_table_trends)
        self.t_advice = self._ddb.Table(SETTINGS.ddb_table_advice)
        self.t_replies = self._ddb.Table(SETTINGS.ddb_table_replies)
        self.t_feedback = self._ddb.Table(SETTINGS.ddb_table_feedback)
        self.bucket = SETTINGS.s3_bucket_raw

    @staticmethod
    def _clean(d: dict[str, Any]) -> dict[str, Any]:
        # DynamoDB rejects float; our floats (confidence, severity) fit in Decimal
        # via json round-trip with parse_float. Simplest: string-encode then decode.
        return json.loads(json.dumps(d), parse_float=str)

    # raw + extracted ---------------------------------------------------------- #
    def put_raw_review(self, raw: RawReview) -> None:
        if raw.ingested_at is None:
            raw = raw.model_copy(update={"ingested_at": _now()})
        key = f"{raw.business_id}/{raw.review_id}.json"
        self._s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=raw.model_dump_json().encode("utf-8"),
            ContentType="application/json",
        )
        item = self._clean(raw.model_dump(mode="json"))
        item.update({"PK": raw.business_id, "SK": f"RAW#{raw.review_id}",
                     "item_type": "RAW", "s3_key": key})
        self.t_reviews.put_item(Item=item)

    def get_raw_review(self, review_id: str) -> RawReview | None:
        for r in self.list_raw_reviews():
            if r.review_id == review_id:
                return r
        return None

    def list_raw_reviews(self, business_id: str | None = None) -> list[RawReview]:
        rows = self._scan(self.t_reviews, item_type="RAW", business_id=business_id)
        return [RawReview(**{k: v for k, v in r.items()
                             if k in RawReview.model_fields}) for r in rows]

    def put_extracted(self, rec: ExtractedReviewRecord) -> None:
        if rec.extracted_at is None:
            rec = rec.model_copy(update={"extracted_at": _now()})
        item = self._clean(rec.model_dump(mode="json"))
        item.update(rec.ddb_keys())
        item["item_type"] = "EXTRACTED"
        self.t_reviews.put_item(Item=item)

    def list_extracted(
        self, business_id: str | None = None, topic: str | None = None
    ) -> list[ExtractedReviewRecord]:
        rows = self._scan(self.t_reviews, item_type="EXTRACTED", business_id=business_id)
        out = []
        for r in rows:
            clean = {k: v for k, v in r.items() if k in ExtractedReviewRecord.model_fields}
            rec = ExtractedReviewRecord(**clean)
            if topic is None or rec.topic == topic or topic in rec.secondary_topics:
                out.append(rec)
        out.sort(key=lambda r: r.review_date)
        return out

    def log_extraction_error(self, payload: dict[str, Any], error: str) -> None:
        self._s3.put_object(
            Bucket=self.bucket,
            Key=f"_errors/{_now()}-{payload.get('review_id', 'unknown')}.json",
            Body=json.dumps({"error": error, "payload": payload}).encode("utf-8"),
            ContentType="application/json",
        )

    # downstream ----------------------------------------------------------- #
    def _put(self, table, model, key_pk: str, key_sk: str) -> None:
        item = self._clean(model.model_dump(mode="json"))
        item.update({"PK": key_pk, "SK": key_sk})
        table.put_item(Item=item)

    def _scan(self, table, *, item_type: str | None = None,
              business_id: str | None = None) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {}
        resp = table.scan(**kwargs)
        rows = resp.get("Items", [])
        while "LastEvaluatedKey" in resp:
            resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
            rows += resp.get("Items", [])
        if item_type is not None:
            rows = [r for r in rows if r.get("item_type") == item_type]
        if business_id is not None:
            rows = [r for r in rows if r.get("business_id") == business_id]
        return rows

    def put_trend_flag(self, flag: TrendFlag) -> None:
        if flag.detected_at is None:
            flag = flag.model_copy(update={"detected_at": _now()})
        self._put(self.t_trends, flag, flag.business_id, flag.trend_id)

    def list_trend_flags(self, business_id: str | None = None) -> list[TrendFlag]:
        rows = self._scan(self.t_trends, business_id=business_id)
        return [TrendFlag(**{k: v for k, v in r.items()
                             if k in TrendFlag.model_fields}) for r in rows]

    def put_advice(self, advice: AdviceRecord) -> None:
        if advice.created_at is None:
            advice = advice.model_copy(update={"created_at": _now()})
        self._put(self.t_advice, advice, advice.business_id, advice.advice_id)

    def list_advice(self, business_id: str | None = None) -> list[AdviceRecord]:
        rows = self._scan(self.t_advice, business_id=business_id)
        return [AdviceRecord(**{k: v for k, v in r.items()
                                if k in AdviceRecord.model_fields}) for r in rows]

    def put_reply_draft(self, draft: ReplyDraft) -> None:
        if draft.created_at is None:
            draft = draft.model_copy(update={"created_at": _now()})
        self._put(self.t_replies, draft, draft.business_id, draft.reply_id)

    def list_reply_drafts(self, business_id: str | None = None) -> list[ReplyDraft]:
        rows = self._scan(self.t_replies, business_id=business_id)
        return [ReplyDraft(**{k: v for k, v in r.items()
                              if k in ReplyDraft.model_fields}) for r in rows]

    def put_feedback(self, fb: FeedbackLog) -> None:
        if fb.created_at is None:
            fb = fb.model_copy(update={"created_at": _now()})
        self._put(self.t_feedback, fb, fb.business_id, fb.feedback_id)

    def list_feedback(self, business_id: str | None = None) -> list[FeedbackLog]:
        rows = self._scan(self.t_feedback, business_id=business_id)
        return [FeedbackLog(**{k: v for k, v in r.items()
                               if k in FeedbackLog.model_fields}) for r in rows]


# --------------------------------------------------------------------------- #
_repo_singleton: Repository | None = None


def get_repository() -> Repository:
    global _repo_singleton
    if _repo_singleton is None:
        if SETTINGS.storage_backend == "dynamodb":
            _repo_singleton = DynamoDBRepository()
        else:
            _repo_singleton = LocalJSONRepository()
    return _repo_singleton
