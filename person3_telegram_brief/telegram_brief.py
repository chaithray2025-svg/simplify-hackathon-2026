"""
Formats an agent-produced trend JSON (like the one below) into a Telegram-ready
message. This module does NOT call any LLM and does NOT send anything to
Telegram itself — it only turns the JSON into a formatted string. Wire that
string into your own `bot.send_message(chat_id, text, parse_mode="Markdown")`
call when you're ready to actually send it.

Expected input shape (field names can be adjusted if the upstream agent's
schema changes — just update the .get(...) calls below to match):

{
  "topic": "wait_time",
  "weeks": ["2026-W01", "2026-W02", "2026-W03"],
  "weekly_counts": [2, 3, 5],
  "supporting_quotes": [
    {"quote": "...", "date": "2026-01-19"}
  ],
  "trend_summary": "Wait times have been rising for 3 weeks...",
  "advice": "Hire one additional front-of-house staff member...",
  "actionability_check": "PASS"
}
"""

from __future__ import annotations

# --- Config -----------------------------------------------------------------

# Emoji shown next to the actionability_check value. Anything not listed here
# falls back to "❔".
ACTIONABILITY_EMOJI = {
    "PASS": "✅",
    "FAIL": "❌",
    "REVIEW": "⚠️",
}

# Emoji shown in the header, keyed by topic. Falls back to "📊" for unknown
# topics, so new topics from the upstream agent don't need code changes.
TOPIC_EMOJI = {
    "wait_time": "⏱️",
    "food_quality": "🍽️",
    "cleanliness": "🧼",
    "staff_attitude": "🙂",
}

# Characters that need escaping for Telegram's legacy "Markdown" parse mode.
# (Simpler ruleset than MarkdownV2 — fewer characters, no need to escape
# punctuation like "." or "-" that's common in ordinary text/quotes.)
_MD_SPECIAL_CHARS = "_*`["


def escape_markdown(text: str) -> str:
    """Escape characters that are special in Telegram's legacy Markdown mode."""
    for ch in _MD_SPECIAL_CHARS:
        text = text.replace(ch, f"\\{ch}")
    return text


def _topic_title(topic: str) -> str:
    """'wait_time' -> 'Wait Time'."""
    return topic.replace("_", " ").title()


def format_brief(data: dict) -> str:
    """
    Turn one agent-output record into a formatted Telegram message
    (Telegram legacy Markdown syntax — send with parse_mode="Markdown").
    """
    topic = data.get("topic", "update")
    weeks = data.get("weeks", [])
    weekly_counts = data.get("weekly_counts", [])
    quotes = data.get("supporting_quotes", [])
    trend_summary = data.get("trend_summary", "")
    advice = data.get("advice", "")
    actionability = data.get("actionability_check", "")

    emoji = TOPIC_EMOJI.get(topic, "📊")
    action_emoji = ACTIONABILITY_EMOJI.get(actionability, "❔")

    lines = [f"{emoji} *{escape_markdown(_topic_title(topic))} — Weekly Trend*", ""]

    # Weekly counts table
    for week, count in zip(weeks, weekly_counts):
        lines.append(f"• {escape_markdown(week)}: {count} mention{'s' if count != 1 else ''}")
    if weeks:
        lines.append("")

    # Trend summary
    if trend_summary:
        lines.append(f"📈 *Trend:* {escape_markdown(trend_summary)}")
        lines.append("")

    # Advice — the actionable recommendation
    if advice:
        lines.append("💡 *Recommended action:*")
        lines.append(escape_markdown(advice))
        lines.append("")

    # Supporting quotes (optional, only if present)
    if quotes:
        lines.append("🗣️ *Supporting quotes:*")
        for q in quotes:
            quote_text = escape_markdown(q.get("quote", ""))
            date = q.get("date", "")
            suffix = f" ({date})" if date else ""
            lines.append(f"_{quote_text}_{suffix}")
        lines.append("")

    # Actionability badge
    if actionability:
        lines.append(f"{action_emoji} Actionability: *{escape_markdown(actionability)}*")

    return "\n".join(lines).strip()


if __name__ == "__main__":
    example = {
        "topic": "wait_time",
        "weeks": ["2026-W01", "2026-W02", "2026-W03"],
        "weekly_counts": [2, 3, 5],
        "supporting_quotes": [
            {"quote": "We waited almost 30 minutes just to be seated.", "date": "2026-01-19"}
        ],
        "trend_summary": "Wait times have been rising for 3 weeks, with mentions increasing from 2 to 5 per week.",
        "advice": "Hire one additional front-of-house staff member specifically for the 12:00-13:30 lunch window when wait times are peaking at 25-30 minutes.",
        "actionability_check": "PASS",
    }

    print(format_brief(example))
