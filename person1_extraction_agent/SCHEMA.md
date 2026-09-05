# SCHEMA.md — data contract

**Owner:** Person 1. **Status:** locked for Day 1. Changes after this point must be
announced in the team channel because Person 2 (Trend + Advice) and Person 3
(Reply + Orchestration + Telegram) both read and write against these shapes.

Everything here is the source of truth for:

- the Pydantic models in `src/simplifynext/models.py`
- the DynamoDB table design (real backend)
- the local JSON store (`data/store/*.json`, dev backend — same record shapes)

All timestamps are ISO-8601 UTC strings (`2026-09-01T12:34:00Z`). All dates are
`YYYY-MM-DD`. "ISO week" means `GGGG-Www` (e.g. `2026-W36`), computed from the
review date with `datetime.date.isocalendar()`.

---

## 0. Controlled vocabulary — `topic`

The Extraction Agent MUST map every review to exactly one primary `topic` from
this list (and MAY add more in `secondary_topics`). Trend Detection groups on
`topic`, so the value has to come from a closed set — free-text topics break the
grouping.

| topic | covers |
|---|---|
| `food_quality` | taste, freshness, cooking (undercooked/overcooked), stale |
| `food_temperature` | served cold / lukewarm when it should be hot |
| `portion_size` | too small / too large for the price |
| `menu_variety` | limited choice, items unavailable, no vegetarian/halal option |
| `price_value` | too expensive, surcharges, value for money |
| `wait_time` | queue to be seated, time from order to food, long bill wait |
| `service_attentiveness` | ignored, hard to flag staff, slow refills |
| `staff_friendliness` | rude, warm, went out of their way |
| `order_accuracy` | wrong item, missing item, allergy/request ignored |
| `cleanliness` | dirty table, cutlery, toilet, floor |
| `ambience_noise` | too loud, too dark, music, crowding, smell |
| `seating_comfort` | cramped, wobbly table, aircon too cold/hot |
| `reservation_booking` | booking not honoured, no-show handling, phone unanswered |
| `payment_checkout` | card declined, no PayNow, split-bill refusal, slow POS |
| `delivery_takeaway` | late delivery, spillage, packaging, missing items (off-premise) |
| `hygiene_safety` | foreign object in food, pest sighting, food poisoning claim |
| `other` | anything genuinely outside the list — use sparingly |

`sentiment` is one of: `positive`, `neutral`, `negative`, `mixed`.

`language` is a BCP-47 primary subtag, restricted for this project to:
`en`, `zh`, `ta`, `ms`, `other`.

---

## 1. RawReview  (input)

The unprocessed review as ingested. Stored verbatim so we can re-run extraction
after prompt changes.

- **DynamoDB:** table `DDB_TABLE_REVIEWS`, item type `RAW`
  - `PK = business_id`
  - `SK = "RAW#" + review_id`
- **S3 (real backend only):** the full JSON is also written to
  `s3://$S3_BUCKET_RAW/{business_id}/{review_id}.json` as an immutable copy.
  The DynamoDB item carries `s3_key` pointing at it.
- **Local backend:** `data/store/raw_reviews.json`, keyed by `review_id`.

```jsonc
{
  "review_id": "g_ChdDSUhN...",      // string, stable id from the source platform
  "business_id": "sg-hawker-042",     // string, our internal id for the outlet
  "source": "google",                 // google | facebook | tripadvisor | manual | seed
  "review_date": "2026-08-30",        // YYYY-MM-DD, when the customer posted it
  "ingested_at": "2026-09-01T02:00:00Z",
  "rating": 2,                         // int 1..5, or null if the source has no stars
  "author_name": "J. Tan",            // string or null
  "text": "等了45分钟菜才来，服务员态度也不好。",   // original text, UNMODIFIED, any language
  "s3_key": "sg-hawker-042/g_ChdDSUhN.json"   // present only on dynamodb backend
}
```

---

## 2. ExtractedReviewRecord  (Extraction Agent output — Person 1)

One per RawReview. This is the **Extracted Review Record** the plan refers to.

- **DynamoDB:** table `DDB_TABLE_REVIEWS`, item type `EXTRACTED`
  - `PK = business_id`
  - `SK = "EXT#" + review_id`
  - **GSI1** (for Trend Detection): `GSI1PK = business_id + "#" + topic`,
    `GSI1SK = review_date`  → lets Person 2 pull every review for one topic in
    date order without a full scan.
- **Local backend:** `data/store/extracted_reviews.json`, keyed by `review_id`.

```jsonc
{
  "review_id": "g_ChdDSUhN...",       // FK to RawReview
  "business_id": "sg-hawker-042",
  "review_date": "2026-08-30",
  "iso_week": "2026-W35",              // derived, stored for cheap grouping
  "extracted_at": "2026-09-01T02:03:11Z",
  "model_id": "global.anthropic.claude-haiku-4-5-20251001-v1:0",
  "schema_version": 1,

  "language": "zh",                    // detected original language (see §0)
  "is_translated": true,               // true if text fields below were translated to English
  "text_en": "Waited 45 minutes for the food, and the server had a bad attitude.",
  "text_original": "等了45分钟菜才来，服务员态度也不好。",  // copy of RawReview.text

  "sentiment": "negative",             // positive | neutral | negative | mixed
  "rating": 2,                         // carried over from RawReview (int or null)

  "topic": "wait_time",               // PRIMARY topic, controlled vocab
  "secondary_topics": ["staff_friendliness"],  // 0..3 more from the controlled vocab

  "entities": [                        // concrete things named in the review
    {
      "kind": "wait_time",           // one of: menu_item | staff_role | staff_name |
                                      //   location_area | time_slot | wait_time |
                                      //   price | competitor | other
      "value": "45 minutes",         // verbatim-ish span, translated to English
      "sentiment": "negative"        // sentiment attached to THIS entity
    },
    { "kind": "staff_role", "value": "server", "sentiment": "negative" }
  ],

  "time_slot": "unknown",             // if the review implies a daypart:
                                      //   breakfast | lunch | tea | dinner | late_night | unknown
  "actionable_quote": "Waited 45 minutes for the food",  // the single most useful sentence, English
  "confidence": 0.82                   // 0..1, model's self-reported extraction confidence
}
```

### Validation rules (enforced in code, not left to the LLM)

1. `topic` ∈ controlled vocab, else the record is rejected and logged.
2. `secondary_topics` ⊆ controlled vocab, deduped, `topic` removed from it, max 3.
3. `language` ∈ {en, zh, ta, ms, other}.
4. `is_translated == (language != "en")` unless `language == "other"`.
5. `text_en` non-empty. If `language == "en"`, `text_en == text_original`.
6. `entities[].kind` ∈ the closed set above; max 8 entities.
7. `sentiment` and every `entities[].sentiment` ∈ the sentiment enum.
8. `confidence` ∈ [0, 1].
9. On any failure: write nothing to the store, append the raw payload +
   error to `data/store/extraction_errors.json` (local) / CloudWatch log
   (real). Never silently drop.

---

## 3. TrendFlag  (Trend Detection Agent output — Person 2)

Emitted when a topic's negative-mention count is **strictly increasing across ≥3
consecutive ISO weeks** and the **latest week has ≥2 mentions**.

- **DynamoDB:** table `DDB_TABLE_TRENDS`
  - `PK = business_id`
  - `SK = trend_id`  where `trend_id = topic + "#" + detected_week`
- **Local backend:** `data/store/trend_flags.json`, keyed by `trend_id`.

```jsonc
{
  "trend_id": "wait_time#2026-W35",
  "business_id": "sg-hawker-042",
  "detected_at": "2026-09-01T02:05:00Z",
  "detected_week": "2026-W35",         // latest week in the window
  "topic": "wait_time",

  "window_weeks": ["2026-W33", "2026-W34", "2026-W35"],
  "weekly_counts": [2, 3, 5],          // negative mentions per week, aligned to window_weeks
  "direction": "worsening",            // worsening | improving | flat  (Person 2 may also emit improving)
  "severity": 0.71,                    // 0..1, function of slope + volume (Person 2's formula)

  "summary": "Complaints about wait time have risen for 3 consecutive weeks (2 → 3 → 5).",
  "evidence": [                        // pulled straight from ExtractedReviewRecord, NOT model-invented
    { "review_id": "g_Abc...", "review_date": "2026-08-30",
      "quote": "Waited 45 minutes for the food", "language": "zh" },
    { "review_id": "g_Def...", "review_date": "2026-08-28",
      "quote": "Queue was out the door at lunch", "language": "en" }
  ],
  "status": "open"                     // open | advised | resolved | dismissed
}
```

---

## 4. AdviceRecord  (Advice Agent output — Person 2)

One per TrendFlag. Consumes §3, produces one specific fix.

- **DynamoDB:** table `DDB_TABLE_ADVICE`
  - `PK = business_id`
  - `SK = advice_id`  where `advice_id == trend_id`  (1:1)
- **Local backend:** `data/store/advice.json`, keyed by `advice_id`.

```jsonc
{
  "advice_id": "wait_time#2026-W35",   // == trend_id
  "trend_id": "wait_time#2026-W35",
  "business_id": "sg-hawker-042",
  "created_at": "2026-09-01T02:06:30Z",
  "model_id": "global.anthropic.claude-sonnet-4-5-20250929-v1:0",

  "topic": "wait_time",
  "advice": "Add one runner to the 12:00–13:30 lunch service Thu–Sun; that window holds 4 of the last 5 wait-time complaints.",
  "rationale": "Evidence quotes cluster at lunch on weekends; kitchen throughput is fine, the gap is table-to-runner coverage.",

  "actionability": {                   // checked in code AFTER generation
    "has_time_or_daypart": true,
    "has_staff_role_or_headcount": true,
    "has_menu_item": false,
    "passes_bar": true                 // true if at least one of the above is present
  },

  "expected_metric": "wait_time negative mentions / week",
  "baseline_value": 5,                 // latest weekly count at time of advice
  "target_value": 2,                   // what "the fix worked" looks like
  "review_after_week": "2026-W37",     // when the Monday brief should check if it worked
  "status": "proposed"                 // proposed | sent | accepted | rejected | verified
}
```

---

## 5. ReplyDraft  (Reply Drafting Agent output — Person 3)

One per review we choose to answer (negative or mixed, or owner-requested).

- **DynamoDB:** table `DDB_TABLE_REPLIES`
  - `PK = business_id`
  - `SK = reply_id`  where `reply_id == review_id`  (1:1)
- **Local backend:** `data/store/reply_drafts.json`, keyed by `reply_id`.

```jsonc
{
  "reply_id": "g_ChdDSUhN...",         // == review_id
  "review_id": "g_ChdDSUhN...",
  "business_id": "sg-hawker-042",
  "created_at": "2026-09-01T02:07:00Z",
  "model_id": "global.anthropic.claude-haiku-4-5-20251001-v1:0",

  "reply_language": "zh",              // draft written in the review's original language
  "reply_text": "陈先生，非常抱歉让您久等...",
  "reply_text_en": "Mr Tan, we're very sorry about the long wait...",  // always provide English for the owner
  "tone": "apologetic",               // apologetic | grateful | neutral | corrective
  "references_fix": true,              // does it mention a concrete change? (ties to AdviceRecord)
  "status": "draft"                   // draft | approved | edited | rejected | posted
}
```

---

## 6. FeedbackLog  (Telegram tap-approve write-back — Person 3)

Every owner action on a drafted reply or a piece of advice. This is the
human-in-the-loop record that answers "not as accurate as humans".

- **DynamoDB:** table `DDB_TABLE_FEEDBACK`
  - `PK = business_id`
  - `SK = feedback_id`  (uuid4)
- **Local backend:** `data/store/feedback.json`, keyed by `feedback_id`.

```jsonc
{
  "feedback_id": "b1c2...-uuid",
  "business_id": "sg-hawker-042",
  "created_at": "2026-09-01T08:03:12Z",
  "actor": "owner",                   // owner | system
  "target_type": "reply_draft",       // reply_draft | advice | trend_flag
  "target_id": "g_ChdDSUhN...",       // reply_id / advice_id / trend_id
  "action": "approved",               // approved | rejected | edited | snoozed
  "edited_text": null,                 // present only when action == "edited"
  "note": null,
  "brief_id": "2026-W36"               // which Monday brief this action came from
}
```

---

## 7. WeeklyBrief  (assembled by Person 3, not persisted as a first-class record for the hackathon)

Built at send time by joining §3/§4/§5 for a `business_id` over the trailing
week. Shape kept here so the Telegram formatter and the mock data agree.

```jsonc
{
  "brief_id": "2026-W36",
  "business_id": "sg-hawker-042",
  "generated_at": "2026-09-07T00:00:00Z",
  "got_worse": [ /* TrendFlag with direction=worsening + its evidence */ ],
  "one_fix": { /* the single highest-severity AdviceRecord */ },
  "whats_working": [ /* TrendFlag with direction=improving, or top positive topic */ ],
  "last_fix_check": {
    "advice_id": "wait_time#2026-W33",
    "worked": true,
    "baseline_value": 5,
    "current_value": 2
  },
  "draft_replies": [ /* up to 3 ReplyDraft, each with an approve/reject callback id */ ],
  "runway": {                          // optional stretch feature ("what's on the line")
    "monthly_fixed_cost_sgd": 18000,   // rent + salaries + utilities, owner-entered
    "schemes": [ /* up to 3 AdviceRecord-like plans with cost/impact */ ]
  }
}
```

---

## Table summary (real DynamoDB backend)

| env var | table | PK | SK | GSI |
|---|---|---|---|---|
| `DDB_TABLE_REVIEWS` | reviews (RAW + EXTRACTED) | `business_id` | `RAW#…` / `EXT#…` | GSI1: `business_id#topic` / `review_date` |
| `DDB_TABLE_TRENDS` | trend flags | `business_id` | `topic#week` | — |
| `DDB_TABLE_ADVICE` | advice | `business_id` | `= trend_id` | — |
| `DDB_TABLE_REPLIES` | reply drafts | `business_id` | `= review_id` | — |
| `DDB_TABLE_FEEDBACK` | feedback log | `business_id` | `uuid4` | — |

All tables: `PAY_PER_REQUEST` billing, no provisioned capacity. Well inside the
US$20 budget for a hackathon (a few thousand items ≈ cents).
