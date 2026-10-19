# PXE network boot (netboot.xyz) → Proxmox VE reinstalls

Host: **`cash`** (`10.1.30.8`, x86_64, VLAN 30 / Miller Internal).
Chosen because: (a) the arm64 `netboot.xyz` image hangs, and (b) the target
machines are on the same L2 broadcast domain.

```
PXE client (pve/vcm) ──DHCP:67──> dnsmasq (proxyDHCP on cash) ──> bootfile per arch
                      ──TFTP:69──> netboot.xyz.efi / .kpxe
                      ──HTTP────> netboot.xyz menu (boot.netboot.xyz) ──> Proxmox VE installer
```

UniFi DHCP is **untouched** — dnsmasq runs in `proxy` mode and only answers PXE
(option 60) clients, so nothing else on VLAN 30 changes behavior.

## Components (on cash, `/opt/netbootxyz`)
| Service | Role | Ports |
|---|---|---|
| `dnsmasq-pxe` | proxyDHCP + TFTP (host network) | `67/udp`, `69/udp` |
| `netbootxyz` | menu/web assets/webapp | `8090` (http), `3000` (ui) |

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
Bootloaders live in `/opt/netbootxyz/tftp/` (fetched from `boot.netboot.xyz`).

## Boot a machine into the installer
1. On the target (`pve` / `vcm`), enter BIOS/UEFI boot menu and choose **Network / PXE**.
2. You should see the **netboot.xyz** menu → *Proxmox VE* → choose the installer.
3. The Proxmox installer runs; proceed with a fresh install.

Targets on VLAN 30 (`10.1.30.0/23`) are covered. For a machine on another VLAN,
either put a PXE relay there or add DHCP `boot server`/`bootfile` options to that
VLAN in UniFi — the MCP exposes `dhcpd_boot_server`/`dhcpd_boot_filename`.

## Rebuild
Deployed standalone on cash for now. To make it declarative, clone `vps-config`
on cash and add a `pi/nodes/cash/` manifest + the `pi-deploy.timer`.

## Notes
- `cash` is the primary container host; this adds only tiny DHCP/TFTP services.
- netboot.xyz's own TFTP (Docker-NAT) is unreliable, which is why TFTP is served by
  the host-networked `dnsmasq-pxe` instead.
