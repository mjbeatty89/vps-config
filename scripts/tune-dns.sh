#!/usr/bin/env bash
# tune-dns.sh — apply the recommended AdGuard + Unbound config on dnspi.
#
# Run ON dnspi as root (or via: ssh root@dnspi 'bash -s' < tune-dns.sh).
# Needs the AdGuard admin password in $ADGUARD_PW.
#
#   ADGUARD_PW='...' ./tune-dns.sh
#
# Idempotent: safe to re-run. Stops AdGuard only if it must edit the YAML; the
# normal path uses the HTTP API and does not stop DNS.
set -euo pipefail

ADGUARD_PW="${ADGUARD_PW:?set ADGUARD_PW to the AdGuard admin password}"
BASE="http://127.0.0.1:8083"

echo "==> AdGuard API: upstreams, filters, allowlist"
ADGUARD_PW="$ADGUARD_PW" python3 - <<'PY'
import os, json, urllib.request, urllib.error, http.cookiejar
BASE="http://127.0.0.1:8083"; PW=os.environ["ADGUARD_PW"]
cj=http.cookiejar.CookieJar(); op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
def req(path, data=None):
    body=json.dumps(data).encode() if data is not None else None
    r=urllib.request.Request(BASE+path, data=body, headers={"Content-Type":"application/json"},
                             method="POST" if data is not None else "GET")
    try:
        with op.open(r, timeout=30) as x:
            raw=x.read()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        return {"_http": e.code, "_body": e.read()[:200].decode(errors="replace")}
req("/control/login", {"name":"admin","password":PW})

dns=req("/control/dns_info")
dns["upstream_dns"]=["127.0.0.1:5335"]
dns["upstream_dns_file"]=""
dns["bootstrap_dns"]=["1.1.1.1","9.9.9.9"]
if "dnssec_enabled" in dns: dns["dnssec_enabled"]=False
if "edns_client_subnet" in dns: dns["edns_client_subnet"]={}
print("  dns_config:", req("/control/dns_config", dns))

for name,url in [
    ("AdGuard DNS filter","https://adguardteam.github.io/AdGuardSDNSFilter/Filters/filter.txt"),
    ("OISD Big","https://big.oisd.nl"),
    ("HaGeZi TIF","https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/tif.txt"),
]:
    print(f"  filter {name}:", req("/control/filtering/add_url", {"name":name,"url":url,"whitelist":False}))
print("  filtering:", req("/control/filtering/config", {"enabled":True,"interval":24}))

allow = ["@@||connectivitycheck.gstatic.com^","@@||connectivitycheck.android.com^",
         "@@||captive.apple.com^","@@||detectportal.firefox.com^",
         "@@||msftconnecttest.com^","@@||www.msftconnecttest.com^","@@||time.windows.com^"]
st=req("/control/filtering/status")
rules=list(st.get("user_rules") or [])
for r in allow:
    if r not in rules: rules.append(r)
print("  set_rules:", req("/control/filtering/set_rules", {"rules":rules}))

for d,a in [("pve.home","10.1.30.13"),("vcm.home","10.1.30.14"),("cash.home","10.1.30.8"),
            ("dnspi.home","10.1.30.100"),("dockernodepi.home","10.1.30.101"),
            ("ha.home","10.1.30.10"),("ai-server.home","10.1.30.9")]:
    req("/control/rewrite/add", {"domain":d,"answer":a})
print("  rewrites:", len(req("/control/rewrite/list") or []))
PY

echo "==> Unbound tuning"
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
  printf "  %-16s " "$h"; dig +short +time=4 @127.0.0.1 "$h" | head -1
done
echo "done."
