#!/usr/bin/env bash
# On-node GitOps deploy. Installed on each Pi, run by pi-deploy.timer every 5 min.
# Declarative: the repo is the source of truth; this script makes the node match it.
set -euo pipefail

REPO="/opt/aadd/vps-config"
BRANCH="main"
NODE="$(hostname)"
LOG="/var/log/pi-deploy.log"

cd "$REPO"
git fetch --quiet origin "$BRANCH"
git reset --hard --quiet "origin/$BRANCH"

NODE_DIR="$REPO/pi/nodes/$NODE"

# 1. role containers (if the node has Docker)
if [[ -f "$NODE_DIR/docker-compose.yml" ]] && command -v docker >/dev/null 2>&1; then
  docker compose -f "$NODE_DIR/docker-compose.yml" -p "pi-$NODE" up -d --remove-orphans
fi

# 2. tailnet exposure (tailscale serve rules)
if [[ -f "$NODE_DIR/serve" ]]; then
  bash "$REPO/pi/apply-serve.sh" "$NODE_DIR/serve"
fi

# 3. node-local setup hook (VLAN legs, services, etc.)
if [[ -x "$NODE_DIR/setup.sh" ]]; then
  bash "$NODE_DIR/setup.sh" || echo "  setup.sh failed"
fi

echo "[$(date)] pi-deploy ok ($NODE)" >> "$LOG"
