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
(`NotAuthorizedOrNotFound`), so this needs the OCI console / a principal with
network rights.

**Console:** Networking ▸ Virtual Cloud Networks ▸ *(VCN)* ▸ Security Lists ▸
*(the subnet's list for `10.0.0.0/24`)* ▸ Add Ingress Rule:

- Source Type: **CIDR Block**
- Source CIDR: **108.254.162.160/32**
- IP Protocol: **UDP**
- Destination Port Range: **5141**
- Stateless: **No**
- Description: `ATT fiber syslog`

Equivalent rule object:

```yaml
source: 108.254.162.160/32
sourceType: CIDR_BLOCK
protocol: "17"          # UDP
isStateless: false
description: ATT fiber syslog (UDP 5141)
udpOptions:
  destinationPortRange: { min: 5141, max: 5141 }
```

Or via OCI CLI (Cloud Shell, using your own creds):

```bash
oci network security-list list --compartment-id "$TENANCY" --vcn-id "$VCN"
# append the rule above to the existing ingress rules and update:
oci network security-list update --security-list-id "$SL_ID" \
  --ingress-security-rules file:///tmp/sl-ingress.json
```

> If the VNIC is in a Network Security Group, update the **NSG** instead:
> `oci network nsg rules add --nsg-id "$NSG" --security-rules file:///tmp/nsg.json`

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
