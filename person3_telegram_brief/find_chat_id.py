"""
One-time helper to find your chat_id.

Before running this:
  1. Open Telegram, find your bot (search for the username you gave it in
     BotFather), and send it any message (e.g. "hi").
  2. Then run this script — it'll print the chat_id(s) it sees.

Usage:
    python3 find_chat_id.py
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv(".env")

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

resp = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates", timeout=10)
resp.raise_for_status()
data = resp.json()

if not data.get("ok"):
    print("Telegram API error:", data)
    raise SystemExit(1)

results = data.get("result", [])
if not results:
    print("No messages seen yet. Send your bot a message on Telegram first, then re-run this.")
    raise SystemExit(0)

seen = set()
for update in results:
    message = update.get("message") or update.get("channel_post")
    if not message:
        continue
    chat = message["chat"]
    chat_id = chat["id"]
    if chat_id in seen:
        continue
    seen.add(chat_id)
    label = chat.get("username") or chat.get("title") or chat.get("first_name") or "unknown"
    print(f"chat_id={chat_id}  ({chat['type']}, {label})")
