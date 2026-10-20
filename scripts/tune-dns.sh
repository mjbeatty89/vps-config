#!/usr/bin/env bash
# tune-dns.sh — apply the recommended AdGuard + Unbound config on dnspi.
#
# YAML-based: no AdGuard password needed. Run ON dnspi as root:
#   ssh root@dnspi 'bash -s' < scripts/tune-dns.sh
#
# Note: AdGuard recompiles filter lists on first start after a change, so :53 can
# take ~25-30s to bind. The script waits for it.
set -euo pipefail

CFG=/mnt/dietpi_userdata/adguardhome/AdGuardHome.yaml
[[ -f "$CFG" ]] || { echo "config not found: $CFG"; exit 1; }

echo "==> stopping AdGuard + backing up"
systemctl stop adguardhome
cp -a "$CFG" "/root/AdGuardHome.yaml.bak.$(date +%s)"

echo "==> editing AdGuardHome.yaml (schema v0.107)"
python3 - "$CFG" <<'PY'
import sys, yaml
p = sys.argv[1]
d = yaml.safe_load(open(p))

# Upstream: local Unbound only; DNSSEC validated there.
dns = d.setdefault("dns", {})
dns["upstream_dns"] = ["127.0.0.1:5335"]
dns["upstream_dns_file"] = ""
dns["bootstrap_dns"] = ["1.1.1.1", "9.9.9.9"]
dns["enable_dnssec"] = False

# Blocklists (balanced).
flt = d.setdefault("filters", [])
tmpl = dict(flt[-1]) if flt else {"enabled": True, "url": "", "name": ""}
mid = max([int(f.get("id", 0)) for f in flt] + [0])
for name, url in [
    ("AdGuard DNS filter", "https://adguardteam.github.io/AdGuardSDNSFilter/Filters/filter.txt"),
    ("OISD Big", "https://big.oisd.nl"),
    ("HaGeZi TIF", "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/tif.txt"),
]:
    f = next((x for x in flt if x.get("url") == url), None)
    if f:
        f["enabled"] = True
    else:
        mid += 1
        n = dict(tmpl); n.update({"id": mid, "enabled": True, "name": name, "url": url})
        flt.append(n)

# Allowlist: captive-portal / connectivity checks (top-level user_rules in v0.107).
allow = ["@@||connectivitycheck.gstatic.com^", "@@||connectivitycheck.android.com^",
         "@@||captive.apple.com^", "@@||detectportal.firefox.com^",
         "@@||msftconnecttest.com^", "@@||www.msftconnecttest.com^",
         "@@||time.windows.com^"]
rules = d.get("user_rules") or []
for r in allow:
    if r not in rules:
        rules.append(r)
d["user_rules"] = rules

# Split-horizon rewrites live under filtering.rewrites in v0.107.
fil = d.setdefault("filtering", {})
fil["blocking_mode"] = "default"
rw = fil.get("rewrites") or []
have = {(x.get("domain"), x.get("answer")) for x in rw}
for dom, ans in [("pve.home", "10.1.30.13"), ("vcm.home", "10.1.30.14"),
                 ("cash.home", "10.1.30.8"), ("dnspi.home", "10.1.30.100"),
                 ("dockernodepi.home", "10.1.30.101"), ("ha.home", "10.1.30.10"),
                 ("ai-server.home", "10.1.30.9")]:
    if (dom, ans) not in have:
        rw.append({"domain": dom, "answer": ans, "enabled": True})
fil["rewrites"] = rw

yaml.safe_dump(d, open(p, "w"), sort_keys=False)
print(f"  filters={len(flt)} rewrites={len(rw)} user_rules={len(rules)}")
PY

echo "==> starting AdGuard (waiting for :53)"
systemctl start adguardhome
for _ in $(seq 1 60); do
  ss -lun 2>/dev/null | grep -q ':53 ' && break
  sleep 1
done

echo "==> tuning Unbound"
cat > /etc/unbound/unbound.conf.d/99-aadd-tuning.conf <<'CONF'
server:
    prefetch: yes
    prefetch-key: yes
    qname-minimisation: yes
    harden-glue: yes
    harden-dnssec-stripped: yes
    harden-below-nxdomain: yes
    harden-referral-path: yes
    aggressive-nsec: yes
    minimal-responses: yes
    rrset-roundrobin: yes
    cache-min-ttl: 300
    cache-max-ttl: 86400
    msg-cache-size: 32m
    rrset-cache-size: 64m
    so-rcvbuf: 1m
    num-threads: 2
CONF
unbound-checkconf
systemctl restart unbound

echo "==> verify"
for h in example.com doubleclick.net pve.home; do
  printf "  %-18s " "$h"; dig +short +time=4 @127.0.0.1 "$h" | head -1
done
echo "done."
