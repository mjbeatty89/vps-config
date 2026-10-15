#!/usr/bin/env python3
"""Configure an Uptime Kuma Telegram notification and attach it to all monitors.

Run with Kuma STOPPED (the caller handles stop/start). Reads token + chat id
from argv or the environment:
  TELEGRAM_BOT_API=... TELEGRAM_CHAT_ID=... kuma-telegram.py
"""
import json
import os
import sqlite3
import sys

DB = os.environ.get("KUMA_DB", "/opt/docker/uptime-kuma/kuma.db")
CHAT = (os.environ.get("TELEGRAM_CHAT_ID") or (sys.argv[1] if len(sys.argv) > 1 else "")).strip()
TOKEN = (os.environ.get("TELEGRAM_BOT_API") or (sys.argv[2] if len(sys.argv) > 2 else "")).strip()
NAME = "telegram"

if not CHAT or not TOKEN:
    print("missing chat id or bot token")
    sys.exit(1)

config = {
    "type": "telegram",
    "telegramBotToken": TOKEN,
    "telegramChatID": CHAT,
    "telegramSendSilently": False,
    "telegramProtectContent": False,
    "telegramMessageThreadId": None,
}
config_json = json.dumps(config)

c = sqlite3.connect(DB)
row = c.execute("SELECT id FROM notification WHERE name = ?", (NAME,)).fetchone()
if row:
    nid = row[0]
    c.execute("UPDATE notification SET active=1, is_default=1, config=? WHERE id=?", (config_json, nid))
    print(f"updated notification #{nid}")
else:
    cur = c.execute(
        "INSERT INTO notification (name, active, user_id, is_default, config) VALUES (?, 1, 1, 1, ?)",
        (NAME, config_json),
    )
    nid = cur.lastrowid
    print(f"created notification #{nid}")

linked = 0
for (mid,) in c.execute("SELECT id FROM monitor"):
    exists = c.execute(
        "SELECT 1 FROM monitor_notification WHERE monitor_id=? AND notification_id=?", (mid, nid)
    ).fetchone()
    if not exists:
        c.execute(
            "INSERT INTO monitor_notification (monitor_id, notification_id) VALUES (?, ?)", (mid, nid)
        )
        linked += 1
c.commit()
print(f"linked notification to {linked} monitors")
c.close()
