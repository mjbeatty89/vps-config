# virtual-tunnel-vnic — VPS Gateway Config

Oracle Cloud Ubuntu 22.04 ARM — Public Gateway (Two-Box Architecture)

**Public IP:** 147.224.179.179  
**Tailscale IP:** 100.67.166.50  
**Tailnet hostname:** virtual-tunnel-vnic

## Architecture

```
Internet → This VPS (147.224.179.179) → Tailscale → Home Lab
                     ↓
                  Caddy (reverse proxy)
                     ↓
              ai.aadd.rocks → VCM:5000
```

## Services

| Service    | Status  | Notes                        |
|------------|---------|------------------------------|
| Caddy      | active  | Reverse proxy, auto-HTTPS    |
| Tailscaled | active  | Exit node, SSH, accept-routes|
| UFW        | active  | SSH/HTTP/HTTPS only          |

## Users

- `ubuntu` — original cloud-init user (kept for recovery)
- `mjb` — primary user, passwordless sudo

## Files

- `caddy/Caddyfile` — Caddy reverse proxy config
- `systemd/ethtool-gro.service` — UDP GRO fix for Tailscale
- `ufw-rules.sh` — Firewall rule reference

## Setup Notes

- Tailscale advertises as exit node: `sudo tailscale up --advertise-exit-node --ssh --accept-routes`
- UDP GRO forwarding fixed via `/etc/systemd/system/ethtool-gro.service`
- 1Password CLI installed (`op`), authenticate with: `op signin`
