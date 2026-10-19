#!/usr/bin/env bash
# Apply `tailscale serve` rules from a file of "<listen-port> <target>" lines.
# Example line:  443  http://127.0.0.1:3000   # comment
# Blank lines and comments (#) are ignored, including trailing comments.
set -euo pipefail

FILE="${1:?usage: apply-serve.sh <rules-file>}"
[[ -f "$FILE" ]] || exit 0

# Only run where tailscale is present.
command -v tailscale >/dev/null 2>&1 || exit 0

while IFS= read -r line || [[ -n "$line" ]]; do
  line="${line%%#*}"                    # strip trailing comment
  read -r port target <<< "$line" || true
  [[ -z "${port:-}" || -z "${target:-}" ]] && continue
  tailscale serve --bg --https="$port" "$target" >/dev/null
  echo "  serve :$port -> $target"
done < "$FILE"
