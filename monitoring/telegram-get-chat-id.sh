#!/usr/bin/env bash
# Discover the Telegram chat id for the notification bot and write it into monitoring/.env
#
# Usage:
#   1. Open Telegram, find your bot (@aadd_home_bot) and send it any message ("hi").
#   2. Run:  ./telegram-get-chat-id.sh
#
# Optionally pass the bot token as $1, otherwise it is read from ../.env or ./env.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$HERE/.env"

TOKEN="${1:-}"
if [[ -z "$TOKEN" ]]; then
  # shellcheck disable=SC1090,SC1091
  TOKEN="$(grep -h '^TELEGRAM_BOT_API=' "$HERE/../.env" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2-)"
fi
[[ -n "$TOKEN" ]] || { echo "No bot token found (looked in ../.env and ./.env)"; exit 1; }

echo "Polling Telegram getUpdates (send the bot a message now if you haven't)..."
RESP="$(curl -s --max-time 15 "https://api.telegram.org/bot${TOKEN}/getUpdates")"

CHAT_ID="$(printf '%s' "$RESP" | python3 -c '
import sys, json
d = json.load(sys.stdin)
if not d.get("ok"):
    print("", end=""); raise SystemExit
ids = []
for u in d.get("result", []):
    m = u.get("message") or u.get("edited_message") or u.get("channel_post") or u.get("my_chat_member") or {}
    c = m.get("chat", {})
    if c.get("id") is not None:
        label = c.get("username") or c.get("title") or c.get("first_name") or ""
        ids.append((c["id"], c.get("type"), label))
for cid, typ, label in ids:
    print(f"  {cid}  ({typ})  {label}", file=sys.stderr)
print(ids[-1][0] if ids else "")
')"

if [[ -z "$CHAT_ID" ]]; then
  echo "No chats found. Send your bot a message in Telegram, then re-run this script."
  exit 1
fi

echo "Using chat id: $CHAT_ID"
if grep -q '^TELEGRAM_CHAT_ID=' "$ENV_FILE"; then
  sed -i "s|^TELEGRAM_CHAT_ID=.*|TELEGRAM_CHAT_ID=${CHAT_ID}|" "$ENV_FILE"
else
  echo "TELEGRAM_CHAT_ID=${CHAT_ID}" >> "$ENV_FILE"
fi
echo "Updated $ENV_FILE"

# Verify delivery
curl -s --max-time 15 "https://api.telegram.org/bot${TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${CHAT_ID}" \
  --data-urlencode "text=✅ aadd VPS alerts are now wired to this chat." \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);print("test message sent" if d.get("ok") else "send failed: "+str(d))'
