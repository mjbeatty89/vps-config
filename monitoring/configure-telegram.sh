#!/usr/bin/env bash
# configure-telegram.sh — wire one Telegram chat id into every alerting surface.
#
# Run after you have a chat id (see telegram-get-chat-id.sh):
#   ./configure-telegram.sh <chat_id>
#
# It updates:
#   * monitoring/.env                            (TELEGRAM_CHAT_ID)
#   * /etc/netdata/health_alarm_notify.conf      (Netdata native Telegram)
#   * monitoring/grafana/provisioning/alerting/  (Grafana contact point + policy)
# and restarts the affected services, then sends a test message.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$HERE/.env"

CHAT_ID="${1:-$(grep -h '^TELEGRAM_CHAT_ID=' "$ENV_FILE" 2>/dev/null | cut -d= -f2-)}"
[[ -n "${CHAT_ID:-}" ]] || { echo "Usage: $0 <chat_id>"; exit 1; }

TOKEN="$(grep -h '^TELEGRAM_BOT_API=' "$HERE/../.env" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2-)"
[[ -n "$TOKEN" ]] || { echo "No TELEGRAM_BOT_API in ../.env or ./.env"; exit 1; }

echo "==> writing TELEGRAM_CHAT_ID into $ENV_FILE"
if grep -q '^TELEGRAM_CHAT_ID=' "$ENV_FILE"; then
  sed -i "s|^TELEGRAM_CHAT_ID=.*|TELEGRAM_CHAT_ID=${CHAT_ID}|" "$ENV_FILE"
else
  echo "TELEGRAM_CHAT_ID=${CHAT_ID}" >> "$ENV_FILE"
fi

echo "==> configuring Netdata (health_alarm_notify.conf)"
sudo tee /etc/netdata/health_alarm_notify.conf >/dev/null <<EOF
# Managed by monitoring/configure-telegram.sh
SEND_TELEGRAM="YES"
TELEGRAM_BOT_TOKEN="${TOKEN}"
TELEGRAM_API_URL="https://api.telegram.org"
TELEGRAM_RETRIES_ON_LIMIT="1"
DEFAULT_RECIPIENT_TELEGRAM="${CHAT_ID}"
EOF
sudo systemctl restart netdata

echo "==> enabling Grafana alerting provisioning"
cd "$HERE/grafana/provisioning/alerting"
for f in contactpoints policies; do
  [[ -f "$f.yml.disabled" ]] && mv -f "$f.yml.disabled" "$f.yml"
done

echo "==> restarting Grafana"
cd "$HERE"
docker compose up -d grafana >/dev/null

echo "==> configuring Uptime Kuma Telegram notification"
docker stop uptime-kuma >/dev/null
sudo cp -p /opt/docker/uptime-kuma/kuma.db "/opt/docker/uptime-kuma/kuma.db.pre-telegram-$(date +%Y%m%d-%H%M%S)"
sudo TELEGRAM_BOT_API="$TOKEN" TELEGRAM_CHAT_ID="$CHAT_ID" python3 "$HERE/kuma-telegram.py"
docker start uptime-kuma >/dev/null

echo "==> test message"
curl -s --max-time 15 "https://api.telegram.org/bot${TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${CHAT_ID}" \
  --data-urlencode "text=✅ aadd VPS alerts wired (Netdata + Grafana + Uptime Kuma)." \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);print("  sent" if d.get("ok") else "  FAILED: "+str(d))'

echo
echo "Done. Netdata, Grafana and all Kuma monitors now notify this chat."

