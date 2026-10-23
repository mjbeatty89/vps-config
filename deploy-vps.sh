#!/bin/bash
# GitOps deploy for the VPS gateway.
# Applied by vps-deploy.timer every 5 minutes (User=mjb, passwordless sudo).
# Pulls vps-config and reconciles: Caddy, the monitoring stack, and watchman.
set -euo pipefail

REPO="/home/mjb/projects/vps-config"
LOG="/home/mjb/deploy.log"
cd "$REPO"

trap 'echo "[$(date)] deploy FAILED at line $LINENO" >> "$LOG"' ERR

# ── Pull latest config ─────────────────────────────────────────────────────
git pull --ff-only origin main

# ── Generated dashboard must match the registry ────────────────────────────
if [ -f "$REPO/scripts/render-homepage.py" ] && python3 -c 'import yaml' >/dev/null 2>&1; then
  python3 "$REPO/scripts/render-homepage.py" --check >/dev/null
fi

# ── Caddy (config is symlinked from /etc/caddy/Caddyfile -> repo) ──────────
sudo caddy validate --config "$REPO/caddy/Caddyfile" --adapter caddyfile >/dev/null
sudo systemctl reload caddy

# ── Monitoring stack ───────────────────────────────────────────────────────
if [ -f "$REPO/monitoring/docker-compose.yml" ]; then
  ( cd "$REPO/monitoring" && docker compose --env-file .env up -d --remove-orphans )
  # reload Prometheus config in place (no container restart)
  curl -sf -X POST http://127.0.0.1:9090/-/reload >/dev/null 2>&1 || true

  # Homepage reads services.yaml at startup; restart only when it changed.
  HOMEPAGE_HASH_FILE="/home/mjb/.homepage-services.sha256"
  if [ -f "$REPO/monitoring/homepage/config/services.yaml" ]; then
    new_hash=$(sha256sum "$REPO/monitoring/homepage/config/services.yaml" | awk '{print $1}')
    old_hash=$(cat "$HOMEPAGE_HASH_FILE" 2>/dev/null || true)
    if [ "$new_hash" != "$old_hash" ]; then
      docker restart homepage >/dev/null 2>&1 || true
      printf '%s\n' "$new_hash" > "$HOMEPAGE_HASH_FILE"
    fi
  fi
fi

# ── watchman agent (reconcile only when files change) ──────────────────────
if [ -f "$REPO/monitoring/watchman/watchman.py" ]; then
  changed=0
  if ! cmp -s "$REPO/monitoring/watchman/watchman.py" /opt/watchman/watchman.py; then
    sudo install -m 0755 "$REPO/monitoring/watchman/watchman.py" /opt/watchman/watchman.py; changed=1
  fi
  if ! cmp -s "$REPO/monitoring/watchman/watchman.service" /etc/systemd/system/watchman.service; then
    sudo install -m 0644 "$REPO/monitoring/watchman/watchman.service" /etc/systemd/system/watchman.service
    sudo systemctl daemon-reload; changed=1
  fi
  [ "$changed" = 1 ] && sudo systemctl restart watchman || true
fi

echo "[$(date)] deploy ok" >> "$LOG"
