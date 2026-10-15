# AT&T Fiber syslog → VPS gateway (UDP 5141)

Goal: the AT&T gateway (BGW320) ships its firewall/system logs to this VPS so the
network agent can watch them.

```
AT&T gateway ──syslog/UDP 5141──> 147.224.179.179 (OCI) ──> host iptables ──> networkopt-syslog
                                                                              └─ /var/log/networkopt/remote-syslog.log
```

## Host side (already in place)

| Piece | Location |
|---|---|
| Collector | `/opt/networkopt-syslog/syslog_listen.py` |
| Service | `networkopt-syslog.service` (UDP `5141`, `Restart=always`, enabled) |
| Log | `/var/log/networkopt/remote-syslog.log` (rotated daily, 14 days) |
| Firewall | iptables `INPUT`: `ACCEPT udp --dport 5141 -s 108.254.162.160/32` (persisted in `/etc/iptables/rules.v4`) |

## OCI ingress — **the missing piece**

The VCN security list (or the NSG on the VNIC, if one is attached) must allow the
inbound packet, otherwise it is dropped before it reaches the host. The instance's
*instance principal* is **not authorised** for `virtual-network-family`
(`NotAuthorizedOrNotFound` on `iam compartment list`, `network vcn list`,
`network security-list list`), and there are **no OCI credentials on the box**, so
this must be applied by a principal with network rights.

### Option A — OCI Console (fastest, ~30 s)

Networking ▸ Virtual Cloud Networks ▸ *(VCN)* ▸ Security Lists ▸ *(the subnet's
list for `10.0.0.0/24`)* ▸ **Add Ingress Rules**, then paste the rule from
[`oci-att-ingress.json`](./oci-att-ingress.json):

- Source Type: **CIDR Block**
- Source CIDR: **108.254.162.160/32**
- IP Protocol: **UDP**
- Destination Port Range: **5141**
- Stateless: **No**
- Description: `ATT fiber syslog`

If the VNIC is in a Network Security Group instead, add the equivalent rule to
that **NSG**.

### Option B — OCI CLI (Cloud Shell / your laptop, with your creds)

```bash
TENANCY=ocid1.tenancy.oc1..aaaa...
SL=ocid1.securitylist.oc1.us-chicago-1.aaaa...   # the subnet's security list
# 1) fetch current rules, 2) append docs/oci-att-ingress.json, 3) update:
oci network security-list get --security-list-id "$SL" > /tmp/sl.json
jq -s '.[0].data."ingress-security-rules" + .[1]' /tmp/sl.json docs/oci-att-ingress.json > /tmp/merged.json
oci network security-list update --security-list-id "$SL" \
  --ingress-security-rules file:///tmp/merged.json
```

### Option C — let the VPS manage it (enables IP auto-update)

Add the instance to a dynamic group and grant it network rights, then I can wire a
DDNS updater that keeps the rule correct when AT&T rotates your IP:

```
# dynamic group
All { instance.id = 'ocid1.instance.oc1.us-chicago-1.anxxeljsnf6673icwi4oijq4djt7ctq62legtvyn67xu6caoxrr5pruruvfq' }

# policy (in the compartment that owns the VCN)
Allow dynamic-group <dg-name> to manage security-lists in compartment <compartment>
Allow dynamic-group <dg-name> to read virtual-network-family in compartment <compartment>
```

### ⚠️ Caveat: the residential IP changes

`108.254.162.160/32` is your home WAN IP. If AT&T rotates it, the rule silently
stops matching. Mitigations:

1. Update both the OCI rule **and** the iptables source when it changes, or
2. Widen the OCI rule and rely on the host firewall + the collector, or
3. Add a dynamic-DNS updater that rewrites both (the VPS could poll the WAN IP and
   patch the OCI security list via a principal **granted** network access).

## Verify

```bash
# on the VPS: watch for arriving packets
sudo tail -f /var/log/networkopt/remote-syslog.log
# from a host that can spoof/send off-network is hard; simplest is to let the
# gateway send and watch the log fill.

# confirm the port is open and the rule persisted
sudo ss -lunp | grep 5141
sudo grep 5141 /etc/iptables/rules.v4
```

## Gateway settings (AT&T BGW320)

Firewall ▸ Packet Filter / Diagnostics ▸ **Syslog**: enable, server
`147.224.179.179`, port `5141`, protocol UDP. (Exact menu varies by firmware.)
