"""Controlled vocabularies. Mirrors SCHEMA.md §0 — keep them in sync."""

from __future__ import annotations

# Primary + secondary review topics. Trend Detection groups on these, so the set
# is closed. Add a value here AND in SCHEMA.md, never only in a prompt.
TOPICS: tuple[str, ...] = (
    "food_quality",
    "food_temperature",
    "portion_size",
    "menu_variety",
    "price_value",
    "wait_time",
    "service_attentiveness",
    "staff_friendliness",
    "order_accuracy",
    "cleanliness",
    "ambience_noise",
    "seating_comfort",
    "reservation_booking",
    "payment_checkout",
    "delivery_takeaway",
    "hygiene_safety",
    "other",
)

SENTIMENTS: tuple[str, ...] = ("positive", "neutral", "negative", "mixed")

# BCP-47 primary subtags we support for Singapore F&B.
LANGUAGES: tuple[str, ...] = ("en", "zh", "ta", "ms", "other")

ENTITY_KINDS: tuple[str, ...] = (
    "menu_item",
    "staff_role",
    "staff_name",
    "location_area",
    "time_slot",
    "wait_time",
    "price",
    "competitor",
    "other",
)

TIME_SLOTS: tuple[str, ...] = (
    "breakfast",
    "lunch",
    "tea",
    "dinner",
    "late_night",
    "unknown",
)

TOPIC_GLOSS: dict[str, str] = {
    "food_quality": "taste, freshness, under/overcooked, stale",
    "food_temperature": "served cold or lukewarm when it should be hot",
    "portion_size": "portion too small or too large for the price",
    "menu_variety": "limited choice, item unavailable, no veg/halal option",
    "price_value": "too expensive, surcharges, value for money",
    "wait_time": "queue to be seated, order-to-food time, long wait for the bill",
    "service_attentiveness": "ignored, hard to flag staff down, slow refills",
    "staff_friendliness": "rude or warm staff, went out of their way",
    "order_accuracy": "wrong item, missing item, allergy or request ignored",
    "cleanliness": "dirty table, cutlery, toilet, floor",
    "ambience_noise": "too loud, too dark, music, crowding, smell",
    "seating_comfort": "cramped, wobbly table, aircon too cold or hot",
    "reservation_booking": "booking not honoured, no-show handling, phone unanswered",
    "payment_checkout": "card declined, no PayNow, split-bill refusal, slow POS",
    "delivery_takeaway": "late delivery, spillage, packaging, missing items off-premise",
    "hygiene_safety": "foreign object in food, pest sighting, food poisoning claim",
    "other": "genuinely outside the list — use sparingly",
}
