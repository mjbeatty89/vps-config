# Homelab Shape — Outside View

Last updated: 2026-10-23  
Perspective: the Oracle VPS as the always-on public ingress / monitoring / Tailscale hub.

This is a topology and placement snapshot, not a secret inventory. Private addresses
are documented; credentials stay in 1Password or root-only files.

## 1. Role split

| Layer | Primary role |
|---|---|
| **Oracle VPS** | Public ingress (Caddy), monitoring (Prometheus/Grafana/Netdata/Kuma), Homepage, Tailscale exit node, remote access |
| **pve** | Stable service host: LXC/VM workloads, local VM storage, PBS client |
| **pvevcm** | Experiments + DNS secondary (`dns2`), PBS reachable, backup exit node |
| **PBS** | Proxmox backup datastore; offsite copy target pending |
| **TrueNAS** | Bulk storage + NFS for VM disks (LAN path currently broken; tailnet works) |
| **Unraid** | Media array + cache; media apps and Docker workloads planned |
| **cash** | PXE/netboot, MCP control plane, dashboards, Resume, syslog receiver |
| **ai-server** | GPU inference, Hermes Agent, jev-router, llama.cpp, ODS/AI extras |
| **dnspi / dockernodepi** | AdGuard + Unbound primary; cAdvisor/mDNS |
| **dns2** | Secondary AdGuard/Unbound on pvevcm |

## 2. Topology

```text
                         Internet
                            │
                    Oracle VPS (public)
              Caddy / monitoring / Kuma / homepage
                     Tailscale exit + hub
                            │
                 Tailnet manee-frog.ts.net
        ┌───────────────┬───────────────┬───────────────┐
        │               │               │               │
      pve            pvevcm           PBS           TrueNAS
  10.1.30.13       10.1.30.15      10.1.30.14      10.1.30.11
  LXC 120/121/122  dns2 LXC 110    backups        NFS / bulk
        │               │
        └────── 10.1.30.0/23 ───────┐
                                    │
                       cash 10.1.30.8   ai-server 10.1.30.9
                       PXE / MCP / UI    GPU / Hermes / OmniRoute
                                    │
                       dnspi .100      dockernodepi .101
                       AdGuard/Unbound cAdvisor / mDNS
```

### Nodes

| Node | LAN | Tailscale | Notes |
|---|---|---|---|
| oracle (VPS) | public `147.224.179.179` | `100.67.166.50` | Caddy, monitoring, exit node |
| pve | `10.1.30.13` | `100.87.215.43` | PVE 9.2.21; 15 GB RAM; `local-lvm` 365 GB, `vmstore` 241 GB |
| pvevcm | `10.1.30.15` | `100.66.106.75` | PVE 9.2.21; 15 GB RAM; 135 GB `local-lvm`; PBS active |
| PBS | `10.1.30.14` | — | PBS 4.2.8; `rpool` 911 GB, 7.2 GB used |
| TrueNAS | `10.1.30.11` | `100.102.150.25` | LAN TCP broken; tailnet 22/80/2049 work |
| Unraid | `10.1.30.16` | `100.76.50.59` | 3.8 TB array + 477 GB cache; parity sync in progress |
| cash | `10.1.30.8` | `100.102.64.18` | PXE, MCP, dashboards, Resume, syslog |
| ai-server | `10.1.30.9` | `100.75.111.86` | GPUs, Hermes, jev-router, llama.cpp, ODS |
| dnspi | `10.1.30.100` | `100.124.162.46` | AdGuard + Unbound primary |
| dockernodepi | `10.1.30.101` | `100.116.201.113` | cAdvisor + VLAN 40 mDNS |
| dns2 | `10.1.30.6` | — | AdGuard/Unbound secondary on pvevcm LXC 110 |
| qdevice | `10.1.31.103` | `100.122.140.11` | corosync-qnetd 3.0.3; quorum vote |

## 3. Tailscale

- Tailnet: `manee-frog.ts.net`
- Roles/tags: `tag:server`, `tag:homelab`, `tag:desktop`, `tag:exit`, `tag:gateway`,
  `tag:remote`.
- Exit nodes: `oracle` (primary), `pvevcm` (backup).
- Subnet routers:
  - TrueNAS → `10.1.30.0/23`
  - pvevcm → `10.1.10.0/23`, `10.1.40.0/23`, `10.1.50.0/24`
- pvevcm has `--accept-routes=false` to avoid the old TrueNAS LAN loop.
- **QDevice:** `qdevice` at `100.122.140.11`, `corosync-qnetd` 3.0.3; qdevice
  clients active on `pve` and `pvevcm`; expected votes **3**, total votes **3**.
  The old `10.1.31.103` path is not listening; cluster qdevice traffic uses the
  tailnet address.
- Monitoring/admin UIs are intended to be tailnet-only; do not expose Grafana,
  Prometheus, Kuma, Homepage, OmniRoute, Termix, or Forgejo on the public VPS.

Tailnet-facing service URLs currently used:

| Service | URL |
|---|---|
| Forgejo | `https://ai-server.manee-frog.ts.net:3443` |
| OmniRoute | `https://ai-server.manee-frog.ts.net:9443` |
| Termix | `https://ai-server.manee-frog.ts.net:8086` |
| Hermes WebUI | `127.0.0.1:8787` on ai-server (tailnet route can be added) |

## 4. DNS

- Primary: `dnspi` (`10.1.30.100`) — AdGuard Home + Unbound.
- Secondary: `dns2` (`10.1.30.6`) on pvevcm.
- DHCP hands out both resolvers on VLAN 30/40.
- AdGuard upstream is local Unbound only; DNSSEC is handled in Unbound.
- Blocklists: AdGuard DNS filter, OISD Big, HaGeZi TIF.
- Rewrites/allowlist are shared between the two AdGuard instances.

## 5. Storage

| Store | Location | Notes |
|---|---|---|
| PBS `rpool` | PBS | 2×2 TB ZFS mirror; `/rpool/backups`; 7.2 GB used |
| pve `local-lvm` | pve | 365 GB thin pool; OmniRoute/Termix/Forgejo roots |
| pve `vmstore` | pve | 241 GB ZFS mirror on 2×256 GB USB SSDs |
| pvevcm `local-lvm` | pvevcm | 135 GB; dns2 LXC |
| TrueNAS NFS | `10.1.30.11:/mnt/vms/proxmox` | `truenas-vms` currently inactive; LAN path broken |
| Unraid array | Unraid | Parity 2 TB X9; WD 1.8 TB + BX500 1 TB + My Passport 1 TB → 3.8 TB |
| Unraid cache | Unraid | 477 GB btrfs |

Unraid details:

- Parity: Crucial X9 2 TB (`sdb`), syncing.
- Disk 1: WD 1.8 TB (`sdd`, XFS).
- Disk 2: BX500 1 TB (`sda`, XFS).
- Disk 3: My Passport 1 TB (`sdf`, XFS; still has ~18 GB old data).
- Cache: 477 GB btrfs.
- ProductCode 1 TB (`sdc`) is wiped but **unassigned**; USB bridge became flaky during
  partitioning. Add later as disk 4 after checking the enclosure.
- Initial parity sync is in progress; do not reboot until complete.

## 6. Service placement

### pve

| Guest | Service | Address |
|---|---|---|
| LXC 120 | OmniRoute + Redis + local-forward | `10.1.30.20:20128` |
| LXC 121 | Termix | `10.1.30.22:8086` |
| LXC 122 | Forgejo | `10.1.30.23:3000` |
| LXC 100 | pve-scripts-local | internal |

### pvevcm

| Guest | Service |
|---|---|
| LXC 110 | `dns2` (AdGuard/Unbound secondary) |

### cash

- `netbootxyz` + `dnsmasq-pxe` (keep PXE on cash; independent of PVE rebuilds)
- MCP stack (UniFi, JEV, betterstr, cash-mcp, docker shim, ntfy)
- dashboards (consolidation pending)
- Resume + Postgres
- `networkopt-udr-syslog`

### ai-server

- Hermes Agent + jev-router + WebUI
- `llama-swap`, `homelab-llama`, `decision-router`
- ODS / ai-extras and the old OmniRoute/Forgejo containers (stopped)
- GPU: RTX 2060 6 GB + GTX 1080 Ti 11 GB

### VPS

- Caddy ingress
- Prometheus, Grafana, Netdata, Uptime Kuma
- Homepage (`https://dash.aadd.rocks`, basic auth; tailnet `:3010`); Heimdall retired
- `watchman` Telegram watchdog
- Tailscale exit node

## 7. Recent moves / decisions

| Date | Change |
|---|---|
| 2026-10-22 | OmniRoute moved ai-server Docker → pve LXC 120; data volume + env copied; old stopped |
| 2026-10-22 | Forgejo moved ai-server Docker → pve LXC 122; 14 MB volume restored; `:3443` serve updated |
| 2026-10-22 | Termix deployed on pve LXC 121 (it was only a compose file on cash, never running) |
| 2026-10-22 | Unraid array rebuilt: parity + WD + BX500 + My Passport + cache; 3.8 TB |
| 2026-10-23 | jev-router upstream repointed to `10.1.30.20:20128`; Hermes prepared models restored |
| 2026-10-23 | OmniRoute MCP switched to management key; 110 tools registered |
| 2026-10-23 | jev-router set live with explicit-model passthrough + `/stats` |
| 2026-10-23 | PBS offsite Borg job installed; initial backup verified |
| 2026-10-23 | QDevice joined at `100.122.140.11`; expected votes 3, quorate |
| pending | TrueNAS storage-plugin evaluation |
| pending | TrueNAS Proxmox storage-plugin evaluation on pvevcm |
| pending | Resume migration to PVE; Unraid media apps |

## 8. Monitoring and backups

- Uptime Kuma + Prometheus + Grafana + Netdata on the VPS.
- PBS backups from `pve` and `pvevcm` at 02:00.
- PBS `truenas-vms` is inactive because TrueNAS LAN TCP is broken; tailnet NFS works.
- Hetzner Storage Box `hetz-vps` (`u696446.your-storagebox.de`, 1 TB, Helsinki)
  is reachable. It supports **Borg, rsync, sftp, and rclone/restic**.
- PBS offsite is configured: ZFS snapshot of PBS `rpool`, Borg backup of
  `/rpool/backups` to `pbs-backups` on the Storage Box, retention
  7 daily / 4 weekly / 6 monthly, `pbs-offsite-borg.timer` daily at 03:30.
  See [pbs-offsite-borg.md](pbs-offsite-borg.md). Initial 7.34 GB backup completed
  in 10m 30s, `borg check` passed, and a chunk restore matched SHA-256 exactly.
  Borg passphrase and key export are in 1Password.

## 9. Known issues / next steps

1. **Unraid parity sync** — let it finish; verify `DISK_INVALID` clears; then add the
   ProductCode 1 TB if the USB bridge is stable.
2. **TrueNAS LAN** — `.11` is dead on 111/2049/22/80/443 while tailnet works. Fix the
   LAN interface/firewall before evaluating the TrueNAS Proxmox plugin.
3. **PBS `sdb`** — ST2000DL003 has reallocated/pending sectors; replace and resilver.
4. **Resume** — still on cash; copy volumes/secrets and update the Caddy route.
5. **Forgejo runner** — remains on ai-server; it reaches the new LXC through `:3443`.
6. **jev-router live/passthrough** — explicit `auto/*` / `subs2free` selections now
   reach OmniRoute; semantic decisions are logged via `/stats` and `/decisions`.
   See [hermes-stack.md](hermes-stack.md).
7. **Secrets hygiene** — rotate the 1Password service-account/Connect tokens; keep the
   OmniRoute management key in 1Password and `.env` only.
8. **Tailscale key expiry** — personal devices are tagged and never expire; untag and
   set 90-day expiry in the admin console if desired.
9. **Hetzner offsite** — complete: initial backup, `borg check`, key export, and a
   chunk restore test all passed. Monitor the 1 TB quota as the datastore grows.
