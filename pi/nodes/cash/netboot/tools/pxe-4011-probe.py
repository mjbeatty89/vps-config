#!/usr/bin/env python3
"""PXE boot-server probe: speak the port-4011 half of the proxyDHCP handshake.

dnsmasq's proxy mode (pxe_uefi_workaround) answers a UEFI client's DISCOVER on
port 67 with a *redirect* only (siaddr set, no file, no option 43) and expects
the client to send a DHCPREQUEST to port 4011 to learn the boot file.

Usage: pxe-4011-probe.py <iface> <secs> <arch> [ciaddr] [bootitem]
  arch     = 7 (x86-64 EFI), 9 (BC EFI), 6 (IA32 EFI), 0 (BIOS)
  ciaddr   = the IPv4 address the real DHCP server gave the client
  bootitem = optional "type:layer" (e.g. 0:0) => adds PXE boot item sub-opt 71
"""
import random
import socket
import struct
import sys
import time

IFACE = sys.argv[1] if len(sys.argv) > 1 else "enp14s0"
SECS = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0
ARCH = int(sys.argv[3]) if len(sys.argv) > 3 else 7
CIADDR = sys.argv[4] if len(sys.argv) > 4 else "10.1.30.183"
BOOTITEM = sys.argv[5] if len(sys.argv) > 5 else None

MAC = bytes([0x02] + [random.randrange(256) for _ in range(5)])
XID = random.randrange(1 << 32)


def opts_bytes(opts):
    out = b"\x63\x82\x53\x63"
    for code, val in opts:
        out += bytes([code, len(val)]) + val
    return out + b"\xff"


def build():
    bootp = struct.pack(
        "!BBBBIHH4s4s4s4s16s64s128s",
        1, 1, 6, 0, XID, 0, 0x8000,
        socket.inet_aton(CIADDR), b"\0" * 4, b"\0" * 4, b"\0" * 4,
        MAC + b"\0" * 10, b"\0" * 64, b"\0" * 128,
    )
    pxe_sub = b"\x06\x01\x08"  # PXE_DISCOVERY_CONTROL = boot server only
    if BOOTITEM:
        t, l = (int(x) for x in BOOTITEM.split(":"))
        pxe_sub += b"\x47\x04" + struct.pack("!HH", t, l)  # sub-opt 71
    opts = opts_bytes([
        (53, b"\x03"),                                        # DHCPREQUEST
        (55, bytes([1, 3, 6, 43, 54, 60, 66, 67, 93, 94, 97])),
        (60, f"PXEClient:Arch:{ARCH:05d}:UNDI:003000".encode()),
        (93, struct.pack("!H", ARCH)),
        (94, b"\x01\x03\x10"),
        (97, b"\x00" + MAC),
        (43, pxe_sub),
    ])
    payload = bootp + opts
    udp = struct.pack("!HHHH", 68, 4011, 8 + len(payload), 0) + payload
    ip = struct.pack(
        "!BBHHHBBH4s4s", 0x45, 0, 20 + len(udp), random.randrange(1 << 16), 0,
        64, 17, 0, socket.inet_aton(CIADDR), socket.inet_aton("255.255.255.255"),
    )
    s = 0
    for i in range(0, 20, 2):
        s += (ip[i] << 8) | ip[i + 1]
    s = (s & 0xFFFF) + (s >> 16)
    s = (s & 0xFFFF) + (s >> 16)
    ip = ip[:10] + struct.pack("!H", (~s) & 0xFFFF) + ip[12:]
    return b"\xff" * 6 + MAC + b"\x08\x00" + ip + udp


def parse_opts(data):
    i, found = 240, {}
    while i < len(data):
        code = data[i]
        if code == 255:
            break
        if code == 0:
            i += 1
            continue
        ln = data[i + 1]
        found[code] = data[i + 2:i + 2 + ln]
        i += 2 + ln
    return found


s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003))
s.bind((IFACE, 0))
s.settimeout(0.5)
s.send(build())
print(f"4011 probe mac {MAC.hex(':')} arch {ARCH} ciaddr {CIADDR} bootitem {BOOTITEM} on {IFACE}")

seen = set()
end = time.time() + SECS
while time.time() < end:
    try:
        pkt = s.recv(4096)
    except socket.timeout:
        continue
    if pkt[12:14] != b"\x08\x00":
        continue
    ihl = (pkt[14] & 0x0F) * 4
    if pkt[14 + 9] != 17:
        continue
    udp = pkt[14 + ihl:]
    sport = struct.unpack("!H", udp[:2])[0]
    body = udp[8:]
    if len(body) < 240 or body[4:8] != struct.pack("!I", XID):
        continue
    src = socket.inet_ntoa(pkt[14 + 12:14 + 16])
    siaddr = socket.inet_ntoa(body[20:24])
    fname = body[108:236].split(b"\0")[0].decode(errors="replace")
    o = parse_opts(body)
    mtype = {1: "DISCOVER", 2: "OFFER", 3: "REQUEST", 5: "ACK"}.get(
        o.get(53, b"\0")[0], o.get(53, b"\0")[0])
    key = (src, sport, siaddr, fname, mtype)
    if key in seen:
        continue
    seen.add(key)
    print(f"\nreply from {src}:{sport} ({mtype})")
    print(f"  siaddr={siaddr} file={fname or '-'}")
    if 54 in o:
        print(f"  server-id={socket.inet_ntoa(o[54])}")
    if 60 in o:
        print(f"  vendor-class={o[60].decode(errors='replace')}")
    if 43 in o:
        print(f"  option43={o[43].hex()}")

if not seen:
    print("NO REPLY on 4011")
