#!/usr/bin/env bash
# Bootstrap a Raspberry Pi node for the aadd tailnet.
#
# Tested on Raspberry Pi OS (bookworm) and Ubuntu Server 24.04 (arm64).
#
# Usage (as root, run from a checkout of vps-config):
#   sudo ./bootstrap.sh --role dns    --hostname pi-dns
#   sudo ./bootstrap.sh --role docker --hostname pi-docker
#
# Options:
#   --role <dns|docker>    What the node is for (affects only post-install hints)
#   --hostname <name>      Tailnet/host name (defaults to current hostname)
#   --user <name>          Non-root user to add to the docker group (default: first non-root login user)
#   --tags <tag:list>      Tailscale tags (needs tagOwners in your ACL + an auth key)
#   --authkey <tskey-...>  Tailscale auth key for non-interactive `tailscale up`
#
set -euo pipefail

ROLE=""
NODE_HOST=""
DOCKER_USER=""
TAGS=""
AUTHKEY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --role) ROLE="$2"; shift 2 ;;
    --hostname) NODE_HOST="$2"; shift 2 ;;
    --user) DOCKER_USER="$2"; shift 2 ;;
    --tags) TAGS="$2"; shift 2 ;;
    --authkey) AUTHKEY="$2"; shift 2 ;;
    *) echo "unknown arg: $1"; exit 1 ;;
  esac
done

[[ "$(id -u)" -eq 0 ]] || { echo "run as root (sudo)"; exit 1; }
[[ -n "$NODE_HOST" ]] || NODE_HOST="$(hostname)"
[[ -n "$DOCKER_USER" ]] || DOCKER_USER="$(awk -F: '$3>=1000 && $3<65534 {print $1; exit}' /etc/passwd || echo "$SUDO_USER")"

echo "==> node=$NODE_HOST role=${ROLE:-none} docker_user=$DOCKER_USER"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ca-certificates curl gnupg git jq

echo "==> installing Docker (official convenience script)"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker
[[ -n "$DOCKER_USER" ]] && usermod -aG docker "$DOCKER_USER" || true

echo "==> installing Tailscale"
if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi
systemctl enable --now tailscaled

echo "==> setting hostname"
hostnamectl set-hostname "$NODE_HOST"

echo "==> bringing up Tailscale (SSH enabled)"
UP_ARGS=(--ssh --hostname="$NODE_HOST" --accept-routes)
[[ -n "$TAGS" ]] && UP_ARGS+=(--advertise-tags="$TAGS")
if [[ -n "$AUTHKEY" ]]; then
  UP_ARGS+=(--auth-key="$AUTHKEY")
fi
tailscale up "${UP_ARGS[@]}"

echo "==> waiting for tailnet IP"
for _ in $(seq 1 30); do
  TSIP="$(tailscale ip -4 2>/dev/null || true)"
  [[ -n "$TSIP" ]] && break
  sleep 2
done

echo
echo "==> done. Tailnet IP: ${TSIP:-unknown}"
tailscale status | head -5 || true
echo
case "$ROLE" in
  dns)
    echo "DNS node next steps:"
    echo "  1) sudo sed -i 's/^#\\?DNSStubListener=.*/DNSStubListener=no/' /etc/systemd/resolved.conf && sudo systemctl restart systemd-resolved"
    echo "  2) cd home-dns && sudo docker compose up -d"
    echo "  3) open http://${TSIP:-<tailnet-ip>}:3000 and finish the AdGuard wizard (upstream 127.0.0.1:5335)"
    echo "  4) cd ../pi/node-agent && sudo docker compose up -d   # so the VPS can scrape it"
    ;;
  docker)
    echo "Docker node next steps:"
    echo "  1) cd pi/docker-node && cp .env.example .env && sudo docker compose up -d"
    echo "  2) cd ../node-agent && sudo docker compose up -d"
    echo "  3) point LAN/DHCP DNS or other clients as needed"
    ;;
  *)
    echo "Run with --role dns or --role docker for role-specific hints."
    ;;
esac
