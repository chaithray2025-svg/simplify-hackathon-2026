"""
Listens for Approve/Reject button taps and logs them via feedback_log.py.

Long-polls Telegram's getUpdates (simplest option for a hackathon demo —
no public URL / webhook needed). Run this alongside sending reply drafts:

    python3 bot_listener.py

Ctrl+C to stop.
"""

import os
import time
import requests
from dotenv import load_dotenv

from feedback_log import log_feedback

load_dotenv(".env")

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
API = f"https://api.telegram.org/bot{TOKEN}"


def answer_callback_query(callback_query_id: str, text: str) -> None:
    """Dismiss the loading spinner on the tapped button, with a toast message."""
    requests.post(
        f"{API}/answerCallbackQuery",
        json={"callback_query_id": callback_query_id, "text": text},
        timeout=10,
    )


def edit_message_reply_markup(chat_id: str, message_id: int, status_text: str) -> None:
    """Replace the buttons with a plain status line once a decision is made."""
    requests.post(
        f"{API}/editMessageReplyMarkup",
        json={
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": {"inline_keyboard": []},
        },
        timeout=10,
    )
    requests.post(
        f"{API}/sendMessage",
        json={"chat_id": chat_id, "text": status_text},
        timeout=10,
    )


def handle_callback_query(cq: dict) -> None:
    data = cq["data"]  # "approve:r006" or "reject:r006"
    action, review_id = data.split(":", 1)
    chat_id = cq["message"]["chat"]["id"]
    message_id = cq["message"]["message_id"]

    decision = "approved" if action == "approve" else "rejected"
    log_feedback(review_id=review_id, decision=decision, chat_id=str(chat_id))

    answer_callback_query(cq["id"], text=f"Marked {decision}")
    icon = "✅" if decision == "approved" else "❌"
    edit_message_reply_markup(chat_id, message_id, f"{icon} Reply {review_id} {decision}.")

    print(f"[feedback] {review_id} -> {decision}", flush=True)


def poll(interval_seconds: float = 2.0) -> None:
    offset = None
    print("Listening for button taps (Ctrl+C to stop)...", flush=True)
    consecutive_failures = 0
    while True:
        params = {"timeout": 30}
        if offset is not None:
            params["offset"] = offset

        try:
            resp = requests.get(f"{API}/getUpdates", params=params, timeout=35)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            consecutive_failures += 1
            print(f"[warning] Telegram getUpdates failed ({e}); retrying in {interval_seconds}s "
                  f"(failure #{consecutive_failures})", flush=True)
            time.sleep(interval_seconds)
            continue

        consecutive_failures = 0

        for update in data.get("result", []):
            offset = update["update_id"] + 1
            cq = update.get("callback_query")
            if not cq:
                continue
            try:
                handle_callback_query(cq)
            except requests.RequestException as e:
                # Don't let one bad callback (e.g. Telegram edit/answer call
                # failing) kill the whole listener — log and keep polling.
                print(f"[warning] failed to process callback {cq.get('data')}: {e}", flush=True)

        time.sleep(interval_seconds)


if __name__ == "__main__":
    try:
        poll()
    except KeyboardInterrupt:
        print("\nStopped.")