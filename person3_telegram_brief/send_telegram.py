"""
Sends a formatted brief to Telegram.

Usage:
    python3 send_telegram.py <chat_id>

Reads TELEGRAM_BOT_TOKEN from .env (see find_chat_id.py for how to get your
chat_id first).
"""

import os
import sys
import requests
from dotenv import load_dotenv

from telegram_brief import format_brief

load_dotenv(".env")

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]


def send_message(chat_id: str, text: str) -> dict:
    resp = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 send_telegram.py <chat_id>")
        raise SystemExit(1)

    chat_id = sys.argv[1]

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

    result = send_message(chat_id, format_brief(example))
    print("Sent:", result.get("ok"))
