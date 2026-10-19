#!/usr/bin/env bash
# dockernodepi node-local setup (idempotent; run by pi/deploy.sh every 5 min).
#
# 1. Add a VLAN-40 leg so this host sits on both the Internal (30) and IoT (40)
#    broadcast domains. The switch port is already a trunk (native 30, tagged auto).
# 2. Run avahi as an mDNS reflector between eth0 (VLAN 30) and eth0.40 (VLAN 40),
#    so mDNS (Home Assistant on .30 <-> ESP/IoT on .40) crosses VLANs reliably,
#    independent of the UDR's own reflector.
set -euo pipefail

# ── VLAN 40 leg ───────────────────────────────────────────────────────────
if ! ip link show eth0.40 >/dev/null 2>&1; then
  ip link add link eth0 name eth0.40 type vlan id 40
fi
ip link set eth0.40 up

# ── avahi mDNS reflector ──────────────────────────────────────────────────
if [[ -f /etc/avahi/avahi-daemon.conf ]]; then
  sed -i 's/^#\?enable-reflector=.*/enable-reflector=yes/' /etc/avahi/avahi-daemon.conf
  grep -q '^enable-reflector=yes' /etc/avahi/avahi-daemon.conf || \
    sed -i '/^\[reflector\]/a enable-reflector=yes' /etc/avahi/avahi-daemon.conf
  systemctl is-active --quiet avahi-daemon || systemctl restart avahi-daemon
  # restart if the reflector setting changed in this run
  systemctl restart avahi-daemon 2>/dev/null || true
fi
