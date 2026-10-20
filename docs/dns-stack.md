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
| Blocking mode | `default` (0.0.0.0 / ::) | standard; easy to spot in logs |
| EDNS client subnet | off | privacy |
| Query log / statistics | on | needed for tuning + debugging |
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
dig +short @10.1.30.100 doubleclick.net      # 0.0.0.0 (blocked)
dig +short @10.1.30.100 pve.home             # 10.1.30.13
dig +short @127.0.0.1 -p 5335 example.com    # unbound directly
unbound-checkconf                            # config valid
```

## Maintenance
- Filters auto-update daily (AdGuard "Filters update interval").
- False positive → add a custom allow rule (`@@||domain^`) and re-test.
- Watch the Query Log in the AdGuard UI; it's the single best tuning tool.
