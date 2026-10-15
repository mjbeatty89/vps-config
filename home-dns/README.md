# Home DNS node — AdGuard Home + Unbound (Raspberry Pi 4)

This is the **local** half of the DNS design: filtering + recursion on the LAN.
The Oracle VPS keeps the **public authoritative** records (Cloudflare) and the
Caddy reverse proxy; it is *not* the LAN resolver.

```
LAN clients ──53──> AdGuard Home (Pi 4)  ──5335──> Unbound (same Pi, loopback)
   filtering/blocklists                              recursive, DNSSEC, no 3rd-party upstream
```

Why this shape: DNS must be fast and must survive WAN outages, so it lives on
the LAN. AdGuard gives you filtering, per-client rules, and rewrites; Unbound
gives you privacy (your own recursion) and DNSSEC validation.

---

## 1. Prepare the Pi

- **Static IP / DHCP reservation** for the Pi (e.g. `10.0.0.10`). Do this on the
  router/UniFi side, not just on the Pi.
- Disable the systemd-resolved stub listener so port 53 is free:
  ```bash
  sudo sed -i 's/^#\?DNSStubListener=.*/DNSStubListener=no/' /etc/systemd/resolved.conf
  sudo systemctl restart systemd-resolved
  ```
- Allow the Pi to resolve during setup even without the stub:
  `echo 'nameserver 1.1.1.1' | sudo tee /etc/resolv.conf` (Docker will manage it later).
- Install Docker + compose plugin, add your user to the `docker` group.

## 2. Deploy

```bash
git clone git@github.com:mjbeatty89/vps-config.git
cd vps-config/home-dns
sudo docker compose up -d
```

## 3. Finish AdGuard setup (first-run wizard)

Open `http://<pi-ip>:3000` and:

- Set the **admin UI** to listen on `0.0.0.0:3000`, **DNS** on `0.0.0.0:53`.
- Choose an admin username/password.
- **Upstream DNS servers:** replace the defaults with a single entry:
  ```
  127.0.0.1:5335
  ```
  (Unbound is the resolver. Do **not** add 1.1.1.1/8.8.8.8 — that defeats the point.)
- **Bootstrap DNS servers:** `1.1.1.1` / `9.9.9.9` (only used to resolve DoH/DoT
  hostnames; we don't use those, so this is just a fallback).
- Leave AdGuard's own DNSSEC **off** — Unbound validates. (Two validators = confusion.)
- **Blocklists:** add e.g. OISD (https://big.oisd.nl), AdGuard DNS filter, and
  Hagezi Pro (`https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/pro.plus.txt`).
- **Rewrites** (optional split-horizon): point `*.aadd.rocks` (or internal names)
  at the VPS Tailscale/LAN reachable address if you want LAN clients to hit the
  VPS directly.
- If you want the Pi to hand out DNS via DHCP, enable AdGuard's DHCP server and
  disable the router's DHCP; otherwise set the router's DNS to the Pi's IP.

## 4. Point clients at it

- **UniFi:** Settings ▸ Networks ▸ (LAN) ▸ DHCP Name Server → the Pi IP
  (or WAN DNS if you prefer). Set the Pi as primary and a fallback (e.g. the VPS
  AdGuard or `1.1.1.1`) as secondary *only if you accept that fallback bypasses
  filtering*.
- Roaming/tailnet clients can use the **VPS** AdGuard (planned secondary) instead.

## 5. Optional: secondary AdGuard on the VPS (for Tailscale / redundancy)

If you later want filtering for clients that are off-LAN (phones/laptops on the
tailnet), run a second AdGuard on the VPS bound to the Tailscale IP, also
forwarding to a local Unbound. This is a *secondary*, not the primary — LAN
should never depend on the cloud VPS for DNS.

---

## Verify

```bash
# recursion + DNSSEC through unbound
dig @127.0.0.1 -p 5335 cloudflare.com +dnssec
dig @127.0.0.1 -p 5335 dnssec-failed.org        # expect SERVFAIL

# through AdGuard on 53
dig @<pi-ip> example.com
dig @<pi-ip> doubleclick.net                     # expect 0.0.0.0 / NXDOMAIN
```

## Update / backup

- Blocklists + clients + settings live in `home-dns/adguard/conf/AdGuardHome.yaml`.
  Back that file up (e.g. into `vps-config`, which is already a git repo — but it
  contains no upstream secrets, so it is safe).
- Unbound config is this repo's `home-dns/unbound/unbound.conf`.
- This node is bootstrapped by [`../pi/bootstrap.sh`](../pi/bootstrap.sh); see
  [`../pi/README.md`](../pi/README.md) for Tailscale + monitoring wiring.
