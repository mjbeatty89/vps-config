# DNS stack — AdGuard Home + Unbound (recommended config)

`dnspi` (10.1.30.100) runs **AdGuard Home** (filtering + UI) in front of **Unbound**
(recursive resolver, DNSSEC). AdGuard is what you manage; Unbound is tuned via config.

```
clients → AdGuard :53 (block, cache, rewrites) → Unbound 127.0.0.1:5335 (recursion + DNSSEC)
```

## AdGuard settings
| Setting | Value | Why |
|---|---|---|
| Upstream DNS | **`127.0.0.1:5335` only** | all lookups recurse through your Unbound; no third-party DoH |
| Bootstrap DNS | `1.1.1.1`, `9.9.9.9` | only for resolving upstream hostnames (unused with a plain IP upstream) |
| DNSSEC | **off in AdGuard** | Unbound validates; double-validation causes confusing SERVFAILs |
| Blocking mode | `nxdomain` | fast failure for blocked names; avoids clients dialing `0.0.0.0` |
| Rate limit | `100` per client | normal bursty client traffic is not dropped |
| Cache | 64 MB, optimistic on | fewer upstream round-trips; serve stale during resolver hiccups |
| EDNS client subnet | off | privacy |
| Query log / statistics | on, 7-day retention | enough for tuning without a 440 MB log |
| DHCP | off | UniFi handles DHCP |

> **Schema note (v0.107):** rewrites live under `filtering.rewrites`, custom rules
> under top-level `user_rules`, DNSSEC under `dns.enable_dnssec`, and blocking mode
> under `filtering.blocking_mode`. `scripts/tune-dns.sh` handles this for you.

### Blocklists (balanced, low false positives)
| List | URL |
|---|---|
| AdGuard DNS filter | `https://adguardteam.github.io/AdGuardSDNSFilter/Filters/filter.txt` |
| OISD Big | `https://big.oisd.nl` |
| HaGeZi TIF (threats) | `https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/tif.txt` |

Deliberately **not** stacking many overlapping "pro" lists — OISD Big already covers
ads/trackers; HaGeZi TIF adds malware/phishing. Add more only if the query log shows
things getting through.

### Allowlist (prevents "no internet" false positives)
Add as custom filtering rules (`@@` = allow):
```
@@||connectivitycheck.gstatic.com^
@@||connectivitycheck.android.com^
@@||captive.apple.com^
@@||detectportal.firefox.com^
@@||msftconnecttest.com^
@@||www.msftconnecttest.com^
@@||time.windows.com^
```

### Per-client policy
Mal's phone is a persistent client on **both** resolvers:

| Field | Value |
|---|---|
| Client | `Mal-phone` |
| ID | `10.1.30.123` |
| Global settings | off |
| Filtering | **off** |

This keeps strict DNS filtering for the rest of the house while avoiding
anti-adblock popups on her phone. Use **uBlock Origin** in the browser for
cosmetic ad hiding and anti-adblock handling; DNS filtering cannot hide those
popups. A DHCP reservation for `10.1.30.123` (or updating the client ID if the
phone changes address) keeps the policy attached.

### Rewrites (split-horizon)
`pve.home→10.1.30.13`, `vcm.home→10.1.30.14`, `cash.home→10.1.30.8`,
`dnspi.home→10.1.30.100`, `dockernodepi.home→10.1.30.101`, `ha.home→10.1.30.10`,
`ai-server.home→10.1.30.9`.

## Unbound tuning
Managed via `/etc/unbound/unbound.conf.d/99-aadd-tuning.conf`:
- `prefetch: yes`, `prefetch-key: yes`, `qname-minimisation: yes`
- `harden-glue/dnssec-stripped/below-nxdomain/referral-path: yes`, `aggressive-nsec: yes`
- `minimal-responses: yes`, `rrset-roundrobin: yes`
- `cache-min-ttl: 300`, `cache-max-ttl: 86400`
- `msg-cache-size: 32m`, `rrset-cache-size: 64m`, `so-rcvbuf: 1m`, `num-threads: 2`
- listens `127.0.0.1:5335`, access-control localhost only

## Verify
```bash
dig +short @10.1.30.100 example.com          # resolves via unbound
dig +short @10.1.30.100 doubleclick.net      # empty (NXDOMAIN)
dig +noall +comments @10.1.30.100 doubleclick.net | grep status  # NXDOMAIN
dig +short @10.1.30.100 pve.home             # 10.1.30.13
dig +short @10.1.30.6 example.com            # secondary resolver
dig +short @127.0.0.1 -p 5335 example.com    # unbound directly
unbound-checkconf                            # config valid
```

Check the client policy by querying from Mal's phone, then looking for
`10.1.30.123` in the AdGuard query log; filtered requests should show as not
blocked.

## Maintenance
- Filters auto-update daily (AdGuard "Filters update interval").
- False positive → add a custom allow rule (`@@||domain^`) and re-test.
- Watch the Query Log in the AdGuard UI; it's the single best tuning tool.
- Keep both resolvers aligned; DHCP hands out both addresses.

## Rollout notes
| Host | Config | systemd unit |
|---|---|---|
| dnspi | `/mnt/dietpi_userdata/adguardhome/AdGuardHome.yaml` | `adguardhome.service` |
| dns2 | `/opt/AdGuardHome/AdGuardHome.yaml` | `AdGuardHome.service` |

Apply changes with the unit stopped: AdGuard rewrites the YAML on startup and
will overwrite live edits. Keep a timestamped backup next to the config
(`AdGuardHome.yaml.bak.YYYYMMDD-HHMMSS`). After a restart, allow roughly 20–30
seconds for the filter engine to load before port 53 starts listening.
