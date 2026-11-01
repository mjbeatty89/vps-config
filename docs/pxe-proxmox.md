# PXE network boot → Proxmox installs (netboot.xyz + local mirror)

Host: **`cash`** (`10.1.30.8`, x86_64, VLAN 30 / Miller Internal).
Chosen because: (a) the arm64 `netboot.xyz` image hangs, and (b) the target
machines are on the same L2 broadcast domain.

```
PXE client (pve/vcm) ──DHCP:67──> dnsmasq proxyDHCP on cash ──> netboot.xyz.efi / .kpxe
                     ──TFTP:69──> netboot.xyz.efi → menu.ipxe   (our menu, served by cash)
                     ──HTTP:8090─> vmlinuz + initrd + Proxmox ISO (mirrored on cash)
                     ──HTTP:8091─> pve-answers  (automated installs only)
```

UniFi DHCP is **untouched** — dnsmasq runs in `proxy` mode and only answers PXE
(option 60) clients, so nothing else on VLAN 30 changes behavior.

## Components

| Service | Role | Ports |
|---|---|---|
| `dnsmasq-pxe` | proxyDHCP + TFTP (host network) | `67/udp`, `69/udp` |
| `netbootxyz` | webapp UI + nginx serving `/assets` (mirrored ISOs) | `3000`, `8090` |
| `pve-answers` | POST endpoint returning an answer file per MAC | `8091` |

`dnsmasq/dnsmasq.conf`:

```
port=0
dhcp-range=10.1.30.0,proxy
enable-tftp
tftp-root=/tftp
dhcp-match=set:efi64,option:client-arch,7      # x86_64 UEFI
dhcp-match=set:efi64,option:client-arch,9
dhcp-boot=tag:efi64,netboot.xyz.efi,,10.1.30.8
dhcp-match=set:bios,option:client-arch,0       # legacy BIOS
dhcp-boot=tag:bios,netboot.xyz.kpxe,,10.1.30.8
```

## Why there is a local menu

`netboot.xyz.efi` is a stock iPXE build whose embedded script tries, in order:

1. `tftp://<next-server>/local-vars.ipxe`
2. `tftp://<next-server>/HOSTNAME-*.ipxe`, `MAC-*.ipxe`
3. `tftp://<next-server>/menu.ipxe`
4. fallback: `https://boot.netboot.xyz/menu.ipxe`

The old setup shipped only the two bootloaders in the TFTP root, so step 3
always failed and every client booted the upstream **internet** menu. The local
`/opt/netbootxyz-data/config/menus` tree was dormant (the container's own TFTP
is unusable behind Docker NAT).

Now `pi/nodes/cash/netboot/menu.ipxe` is installed into the TFTP root by
`setup.sh`, so the menu itself lives on cash:

| Entry | Boots |
|---|---|
| Proxmox VE 9.2-1 (graphical / text / debug) | mirrored ISO, installer kernel extracted from it |
| Proxmox VE 9.2-1 (unattended) | `prepare-iso --pxe` artifacts + `pve-answers` |
| Proxmox Backup Server 4.2-1 (graphical / text / debug) | mirrored ISO |
| Proxmox Datacenter Manager 1.1-1 (graphical / text / debug) | mirrored ISO |
| netboot.xyz full menu | upstream menu over HTTPS (needs WAN) |

Kernel/initrd are extracted from each ISO's `/boot`; the ISO itself is passed to
the initramfs as a second initrd at `/proxmox.iso`, the same trick netboot.xyz
uses for its asset mirror.

## Boot a machine into the installer

1. On the target (`pve` / `vcm`), enter the firmware boot menu and choose **Network / PXE**.
2. Pick an entry from the **Homelab netboot — cash** menu (60 s timeout → PVE graphical).
3. Proceed with the install.

Targets on VLAN 30 (`10.1.30.0/23`) are covered. For a machine on another VLAN,
either put a PXE relay there or add DHCP `boot server`/`bootfile` options to that
VLAN in UniFi — the MCP exposes `dhcpd_boot_server`/`dhcpd_boot_filename`.

## Unattended installs

Proxmox only automates installs from artifacts prepared by
`proxmox-auto-install-assistant`; a stock ISO cannot be switched to unattended
by kernel parameters alone. `setup.sh` therefore:

1. fetches the assistant (static binary from a pinned, sha256-verified `.deb`)
2. runs `prepare-iso --fetch-from http --url http://10.1.30.8:8091/answer --pxe`
3. installs `vmlinuz` + `initrd.img` into `/opt/netbootxyz-data/assets/proxmox/pve-auto`

`pve-answers` receives the installer's JSON POST and replies with
`answers/<mac>.toml` (lower-case, colon separated), else `answers/default.toml`,
else `404` — which deliberately drops the installer into a shell instead of
guessing which disk to erase.

`answers/default.toml` is **generated at deploy time** with a random root
password (hash injected from `netboot/answers/default.toml.tmpl`; the plain
password lands in `answers/root-password`, mode 0600). No secret is committed.

The default answer installs ZFS (raid0, 64 GiB OS) on `/dev/sda` and powers the
machine off afterwards. Override per machine — the menu entry is labelled
**WIPES DISKS** on purpose.

## Mirror

`pi/nodes/cash/netboot/menu.ipxe` is the single source of truth for the pinned
versions (`set pve_ver`, `set pbs_ver`, `set pdm_ver`); `setup.sh` reads them
and mirrors `proxmox-ve_<ver>.iso`, `proxmox-backup-server_<ver>.iso` and
`proxmox-datacenter-manager_<ver>.iso` (~4.4 GB total) into
`/opt/netbootxyz-data/assets/proxmox/<product>/`, verifying the mirror's
`.sha256` when published.

Sources: `mirrors.tuna.tsinghua.edu.cn/proxmox/iso` (fast), falling back to
`enterprise.proxmox.com/iso`. **Do not use `download.proxmox.com` over HTTPS** —
its certificate is issued for `enterprise.proxmox.com` only, so hostname
verification always fails from cash.

## GitOps

`cash` is managed like the Pis: `pi-deploy.timer` (every 5 min) runs
`pi/deploy.sh`, which syncs `/opt/aadd/vps-config`, runs
`pi/nodes/cash/setup.sh`, then applies `pi/nodes/cash/docker-compose.yml` and
`pi/nodes/cash/dnsmasq/dnsmasq.conf`.

Data lives in `/opt/netbootxyz-data/`:

| Path | Contents |
|---|---|
| `tftp/` | bootloaders + `menu.ipxe` (TFTP root) |
| `config/` | netboot.xyz webapp config (dormant menus) |
| `assets/proxmox/` | mirrored ISOs, extracted kernels, auto-install artifacts |
| `answers/` | PVE answer files + generated root password (not in git) |
| `tools/` | cached `proxmox-auto-install-assistant` |

New ISO version = bump `pve_ver`/`pbs_ver`/`pdm_ver` in `menu.ipxe`, delete the
old ISO + `vmlinuz`/`initrd`, and let the timer re-mirror.

## Notes

- `cash` is the primary container host; this adds only tiny DHCP/TFTP/HTTP services.
- netboot.xyz's own TFTP (Docker-NAT) is unreliable, which is why TFTP is served by
  the host-networked `dnsmasq-pxe` instead.
- The mirrored ISOs are readable by anything on VLAN 30 at `http://10.1.30.8:8090/`.
