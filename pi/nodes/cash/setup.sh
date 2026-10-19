#!/usr/bin/env bash
# cash node-local setup (idempotent; run by pi/deploy.sh before compose).
set -euo pipefail

DATA="/opt/netbootxyz-data"
mkdir -p "$DATA/config" "$DATA/tftp"
chown -R 1000:1000 "$DATA/config" 2>/dev/null || true

cd "$DATA/tftp"
for f in netboot.xyz.efi netboot.xyz.kpxe; do
  if [[ ! -s "$f" ]]; then
    curl -fsSL -o "$f" "https://boot.netboot.xyz/ipxe/$f"
    echo "  fetched $f"
  fi
done
