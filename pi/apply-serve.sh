#!/usr/bin/env bash
# Apply `tailscale serve` rules from a file of "<listen-port> <target>" lines.
# Example line:  443 http://127.0.0.1:3000
# Blank lines and lines starting with # are ignored.
set -euo pipefail

FILE="${1:?usage: apply-serve.sh <rules-file>}"
[[ -f "$FILE" ]] || exit 0

# Only run where tailscale is present.
command -v tailscale >/dev/null 2>&1 || exit 0

while read -r port target; do
  [[ -z "${port:-}" || "$port" == \#* ]] && continue
  [[ -z "${target:-}" ]] && continue
  tailscale serve --bg --https="$port" "$target" >/dev/null
  echo "  serve :$port -> $target"
done < "$FILE"
