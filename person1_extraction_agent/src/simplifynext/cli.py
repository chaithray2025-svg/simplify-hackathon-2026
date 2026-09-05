"""Command line entry point for the Extraction Agent.

    uv run simplifynext extract --input data/synthetic_reviews.json
    uv run simplifynext extract --text "等了45分钟，服务员态度很差" --date 2026-08-30
    uv run simplifynext show --business sg-hawker-042
    uv run simplifynext dump-store
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid

from .config import ROOT, SETTINGS
from .extraction_agent import extract, extract_and_store, run_batch
from .models import ExtractedReviewRecord, RawReview
from .repository import get_repository


def _load_raws(path: str) -> list[RawReview]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return [RawReview(**row) for row in data]


def cmd_extract(args: argparse.Namespace) -> int:
    print(f"provider={SETTINGS.llm_provider}  storage={SETTINGS.storage_backend}  "
          f"model={SETTINGS.model_extraction}")
    if args.text:
        raw = RawReview(
            review_id=args.id or f"cli-{uuid.uuid4().hex[:10]}",
            business_id=args.business,
            source="manual",
            review_date=args.date,
            rating=args.rating,
            text=args.text,
        )
        if args.dry_run:
            res = extract(raw)
        else:
            res = extract_and_store(raw)
        if res.ok:
            print(json.dumps(res.record.model_dump(mode="json"),
                             ensure_ascii=False, indent=2))
            return 0
        print(f"FAILED: {res.error}", file=sys.stderr)
        if res.raw_model_output:
            print(f"raw output:\n{res.raw_model_output}", file=sys.stderr)
        return 1

    if not args.input:
        print("need --input <file.json> or --text <review>", file=sys.stderr)
        return 2

    raws = _load_raws(args.input)
    print(f"extracting {len(raws)} reviews...")
    stats = run_batch(raws)
    print(f"done: {stats['ok']} ok, {stats['error']} error, {stats['total']} total")
    return 0 if stats["error"] == 0 else 1


def cmd_seed(args: argparse.Namespace) -> int:
    """Load the raw seed reviews + the hand-verified golden extractions into the
    store. Gives Person 2 / Person 3 correct offline data without calling Bedrock
    and without depending on the (rough) mock extractor."""
    repo = get_repository()
    raws = _load_raws(str(ROOT / "data" / "synthetic_reviews.json"))
    for raw in raws:
        repo.put_raw_review(raw)
    golden_path = ROOT / "data" / "extracted_reviews.golden.json"
    with open(golden_path, "r", encoding="utf-8") as fh:
        golden = json.load(fh)
    for row in golden:
        repo.put_extracted(ExtractedReviewRecord(**row))
    print(f"seeded {len(raws)} raw reviews + {len(golden)} golden extracted records "
          f"into {SETTINGS.storage_backend} storage")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    repo = get_repository()
    recs = repo.list_extracted(business_id=args.business)
    for r in recs:
        line = (f"{r.review_date}  {r.iso_week}  {r.language:<3}  "
                f"{r.sentiment:<8}  {r.topic:<22}  {r.actionable_quote[:70]}")
        print(line)
    print(f"\n{len(recs)} extracted records"
          + (f" for {args.business}" if args.business else ""))
    return 0


def cmd_dump_store(args: argparse.Namespace) -> int:
    repo = get_repository()
    out = {
        "raw_reviews": [r.model_dump(mode="json") for r in repo.list_raw_reviews()],
        "extracted_reviews": [r.model_dump(mode="json") for r in repo.list_extracted()],
        "trend_flags": [r.model_dump(mode="json") for r in repo.list_trend_flags()],
        "advice": [r.model_dump(mode="json") for r in repo.list_advice()],
        "reply_drafts": [r.model_dump(mode="json") for r in repo.list_reply_drafts()],
        "feedback": [r.model_dump(mode="json") for r in repo.list_feedback()],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="simplifynext")
    sub = p.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("extract", help="run the Extraction Agent")
    pe.add_argument("--input", help="JSON file: list of RawReview objects")
    pe.add_argument("--text", help="a single review string")
    pe.add_argument("--date", default="2026-09-01", help="YYYY-MM-DD for --text")
    pe.add_argument("--business", default="sg-hawker-042")
    pe.add_argument("--rating", type=int, default=None)
    pe.add_argument("--id", default=None)
    pe.add_argument("--dry-run", action="store_true", help="don't write to storage")
    pe.set_defaults(func=cmd_extract)

    pseed = sub.add_parser("seed", help="load raw + golden extracted seed data")
    pseed.set_defaults(func=cmd_seed)

    ps = sub.add_parser("show", help="list extracted records")
    ps.add_argument("--business", default=None)
    ps.set_defaults(func=cmd_show)

    pd = sub.add_parser("dump-store", help="print the whole store as JSON")
    pd.set_defaults(func=cmd_dump_store)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
