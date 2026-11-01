#!/usr/bin/env bash
# cash node-local setup (idempotent; run by pi/deploy.sh before compose).
#
# Prepares everything pi/nodes/cash/netboot/menu.ipxe points at:
#   /opt/netbootxyz-data/tftp/menu.ipxe    iPXE menu served by dnsmasq-pxe (TFTP)
#   /opt/netbootxyz-data/assets/proxmox/   ISOs + kernels served by netbootxyz:8090
#   /opt/netbootxyz-data/answers/          PVE answer files (never committed)
set -euo pipefail

NODE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA="/opt/netbootxyz-data"
ASSETS="$DATA/assets/proxmox"
TFTP="$DATA/tftp"
ANSWERS="$DATA/answers"
TOOLS="$DATA/tools"

# ISO source. TUNA mirrors the Proxmox ISOs at several MB/s;
# enterprise.proxmox.com is the canonical fallback. download.proxmox.com is
# unusable over HTTPS from here: its certificate is issued for
# enterprise.proxmox.com only, so hostname verification always fails.
ISO_MIRROR="${ISO_MIRROR:-https://mirrors.tuna.tsinghua.edu.cn/proxmox/iso}"
ISO_FALLBACK="${ISO_FALLBACK:-https://enterprise.proxmox.com/iso}"

# URL baked into the prepared automated-install image (pve-answers container).
ANSWER_URL="${ANSWER_URL:-http://10.1.30.8:8091/answer}"

# proxmox-auto-install-assistant: static binary, packaged in a ~1 MB .deb.
# Pinned by sha256; the .deb is only fetched when the artifacts are missing.
AI_URL="http://download.proxmox.com/debian/pve/dists/trixie/pve-no-subscription/binary-amd64"
AI_DEB="proxmox-auto-install-assistant_9.0.6_amd64.deb"
AI_SHA256="5720c31f5a8fa1b7b471f32f94e262879b276215d27463771db04bc749af8466"

# menu.ipxe is the single source of truth for the pinned versions.
pve_ver="$(sed -n 's/^set pve_ver //p' "$NODE_DIR/netboot/menu.ipxe")"
pbs_ver="$(sed -n 's/^set pbs_ver //p' "$NODE_DIR/netboot/menu.ipxe")"
pdm_ver="$(sed -n 's/^set pdm_ver //p' "$NODE_DIR/netboot/menu.ipxe")"
: "${pve_ver:?could not read pve_ver from netboot/menu.ipxe}"
: "${pbs_ver:?could not read pbs_ver from netboot/menu.ipxe}"
: "${pdm_ver:?could not read pdm_ver from netboot/menu.ipxe}"

mkdir -p "$DATA/config" "$TFTP" "$ASSETS/pve" "$ASSETS/pbs" "$ASSETS/pdm" \
         "$ASSETS/pve-auto" "$ANSWERS" "$TOOLS"
chown -R 1000:1000 "$DATA/config" 2>/dev/null || true

# --- iPXE menu -------------------------------------------------------------
install -m 0644 "$NODE_DIR/netboot/menu.ipxe" "$TFTP/menu.ipxe"

# --- iPXE bootloaders chained by dnsmasq-pxe -------------------------------
cd "$TFTP"
for f in netboot.xyz.efi netboot.xyz.kpxe; do
  if [[ ! -s "$f" ]]; then
    curl -fsSL -o "$f" "https://boot.netboot.xyz/ipxe/$f"
    echo "  fetched $f"
  fi
done

# --- ISO mirror ------------------------------------------------------------
fetch_iso() {  # fetch_iso <iso-name> <target-dir>
  local name="$1" dir="$2" tmp sum
  [[ -s "$dir/$name" ]] && return 0
  tmp="$dir/$name.part"
  echo "  downloading $name (first deploy only)"
  if ! curl -fL --retry 3 --retry-delay 5 -o "$tmp" "$ISO_MIRROR/$name"; then
    curl -fL --retry 3 --retry-delay 5 -o "$tmp" "$ISO_FALLBACK/$name"
  fi
  sum="$(curl -fsSL "$ISO_MIRROR/$name.sha256" 2>/dev/null | awk 'NR==1{print $1}')"
  if [[ -n "$sum" ]] && ! printf '%s  %s\n' "$sum" "$tmp" | sha256sum -c -; then
    echo "  ERROR: checksum mismatch for $name" >&2
    rm -f "$tmp"
    return 1
  fi
  mv "$tmp" "$dir/$name"
}

extract_boot() {  # extract_boot <iso-path> <target-dir>
  local iso="$1" dir="$2" tmp vmlinuz initrd
  [[ -s "$dir/vmlinuz" && -s "$dir/initrd" ]] && return 0
  command -v xorriso >/dev/null 2>&1 || {
    echo "  WARN: xorriso missing, cannot extract $iso" >&2
    return 0
  }
  tmp="$(mktemp -d)"
  if ! xorriso -osirrox on -indev "$iso" -extract /boot "$tmp/boot" >/dev/null 2>&1; then
    echo "  WARN: could not extract /boot from $iso" >&2
    rm -rf "$tmp"
    return 0
  fi
  # Proxmox ISOs ship /boot/linux26 + /boot/initrd.img; plain Debian
  # installers ship /boot/vmlinuz-* + /boot/initrd.img-*.
  vmlinuz="$(find "$tmp/boot" -maxdepth 1 \\
               \( -name 'vmlinuz*' -o -name 'linux26' -o -name 'linux' \) \\
               | sort -V | tail -1)"
  initrd="$(find "$tmp/boot" -maxdepth 1 -name 'initrd*' | sort -V | tail -1)"
  if [[ -z "$vmlinuz" || -z "$initrd" ]]; then
    echo "  WARN: no kernel/initrd found in $iso" >&2
    rm -rf "$tmp"
    return 0
  fi
  install -m 0644 "$vmlinuz" "$dir/vmlinuz"
  install -m 0644 "$initrd" "$dir/initrd"
  rm -rf "$tmp"
  echo "  extracted $(basename "$vmlinuz") + $(basename "$initrd") -> $dir"
}

# --- automated installation artifacts -------------------------------------
fetch_assistant() {
  [[ -x "$TOOLS/proxmox-auto-install-assistant" ]] && return 0
  command -v bsdtar >/dev/null 2>&1 || return 1
  local tmp
  tmp="$(mktemp -d)"
  if ! curl -fsSL -o "$tmp/ai.deb" "$AI_URL/$AI_DEB"; then
    rm -rf "$tmp"
    return 1
  fi
  if ! printf '%s  %s\n' "$AI_SHA256" "$tmp/ai.deb" | (cd "$tmp" && sha256sum -c -); then
    echo "  ERROR: proxmox-auto-install-assistant checksum mismatch" >&2
    rm -rf "$tmp"
    return 1
  fi
  ( cd "$tmp" && bsdtar xf ai.deb && bsdtar xf data.tar.* )
  install -m 0755 "$tmp/usr/bin/proxmox-auto-install-assistant" \
          "$TOOLS/proxmox-auto-install-assistant"
  rm -rf "$tmp"
}

build_auto() {
  local iso="$ASSETS/pve/proxmox-ve_${pve_ver}.iso" out="$ASSETS/pve-auto" tmp
  [[ -s "$out/vmlinuz" && -s "$out/initrd.img" ]] && return 0
  [[ -s "$iso" ]] || { echo "  skipping auto-install artifacts (no PVE ISO)"; return 0; }
  if ! fetch_assistant; then
    echo "  WARN: proxmox-auto-install-assistant unavailable" >&2
    return 0
  fi
  tmp="$(mktemp -d)"
  if ! "$TOOLS/proxmox-auto-install-assistant" prepare-iso \
        --fetch-from http --url "$ANSWER_URL" --pxe --output "$tmp" "$iso"; then
    echo "  WARN: prepare-iso failed, auto-install entry will not boot" >&2
    rm -rf "$tmp"
    return 0
  fi
  install -m 0644 "$tmp/vmlinuz" "$out/vmlinuz"
  install -m 0644 "$tmp/initrd.img" "$out/initrd.img"
  [[ -s "$tmp/proxmox.iso" ]] && install -m 0644 "$tmp/proxmox.iso" "$out/proxmox.iso"
  rm -rf "$tmp"
  echo "  built PVE auto-install PXE artifacts in $out"
}

# --- answer files ----------------------------------------------------------
generate_default_answer() {
  [[ -s "$ANSWERS/default.toml" ]] && return 0
  local pw hash
  pw="$(openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c 24)"
  hash="$(openssl passwd -6 "$pw")"
  sed "s|@ROOT_PASSWORD_HASH@|$hash|g" \
      "$NODE_DIR/netboot/answers/default.toml.tmpl" > "$ANSWERS/default.toml"
  chmod 0640 "$ANSWERS/default.toml"
  ( umask 077; printf '%s\n' "$pw" > "$ANSWERS/root-password" )
  echo "  generated $ANSWERS/default.toml (root password in $ANSWERS/root-password)"
}
install -m 0644 "$NODE_DIR/netboot/answers/default.toml.example" \
        "$ANSWERS/default.toml.example"

fetch_iso "proxmox-ve_${pve_ver}.iso"              "$ASSETS/pve"
fetch_iso "proxmox-backup-server_${pbs_ver}.iso"  "$ASSETS/pbs"
fetch_iso "proxmox-datacenter-manager_${pdm_ver}.iso" "$ASSETS/pdm"

extract_boot "$ASSETS/pve/proxmox-ve_${pve_ver}.iso"             "$ASSETS/pve"
extract_boot "$ASSETS/pbs/proxmox-backup-server_${pbs_ver}.iso"  "$ASSETS/pbs"
extract_boot "$ASSETS/pdm/proxmox-datacenter-manager_${pdm_ver}.iso" "$ASSETS/pdm"

build_auto
generate_default_answer

# drop stale partial downloads from interrupted deploys
find "$ASSETS" -name '*.part' -mmin +60 -delete 2>/dev/null || true
