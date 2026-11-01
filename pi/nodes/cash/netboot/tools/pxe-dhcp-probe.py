#!/usr/bin/env python3
"""Impersonate a UEFI x86-64 PXE client and dump the DHCP offers it receives.

Sends a DHCPDISCOVER with option 60 = "PXEClient:Arch:00007:UNDI:003000"
and option 93 = 7 (EFI x64) from a random MAC on the LAN NIC, then decodes
every reply. A working proxyDHCP shows up as a second offer from 10.1.30.8
with siaddr=10.1.30.8 and file=netboot.xyz.efi. No lease is committed.
"""
import random
import socket
import struct
import sys
import time

IFACE = sys.argv[1] if len(sys.argv) > 1 else "enp14s0"
SECS = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0
ARCH = sys.argv[3] if len(sys.argv) > 3 else "7"  # 7=EFI x64, 0=BIOS

MAC = bytes([0x02] + [random.randrange(256) for _ in range(5)])
XID = random.randrange(1 << 32)
client_ip = "0.0.0.0"


def dhcp_options(opts):
    out = b"\x63\x82\x53\x63"  # magic cookie
    for code, val in opts:
        out += bytes([code, len(val)]) + val
    out += b"\xff"
    return out


def build():
    bootp = struct.pack(
        "!BBBBIHH4s4s4s4s16s64s128s",
        1, 1, 6, 0, XID, 0, 0x8000,
        socket.inet_aton(client_ip), b"\0" * 4, b"\0" * 4, b"\0" * 4,
        MAC + b"\0" * 10, b"\0" * 64, b"\0" * 128,
    )
    opts = dhcp_options([
        (53, b"\x01"),                       # DHCPDISCOVER
        (55, bytes([1, 3, 6, 43, 54, 60, 66, 67, 93, 94, 97])),
        (60, f"PXEClient:Arch:{int(ARCH):05d}:UNDI:003000".encode()),
        (93, struct.pack("!H", int(ARCH))),  # client system architecture
        (94, b"\x01\x03\x10"),               # UNDI 3.16
        (97, b"\x00" + MAC),                 # client machine identifier
        (43, b"\x06\x01\x08"),                  # PXE discovery control: boot server only
    ])
    payload = bootp + opts
    udp = struct.pack("!HHHH", 68, 67, 8 + len(payload), 0) + payload
    ip = struct.pack(
        "!BBHHHBBH4s4s", 0x45, 0, 20 + len(udp), random.randrange(1 << 16), 0,
        64, 17, 0, socket.inet_aton(client_ip), socket.inet_aton("255.255.255.255"),
    )
    # checksum the header, otherwise every receiver drops the frame
    s = 0
    for i in range(0, 20, 2):
        s += (ip[i] << 8) | ip[i + 1]
    s = (s & 0xFFFF) + (s >> 16)
    s = (s & 0xFFFF) + (s >> 16)
    ip = ip[:10] + struct.pack("!H", (~s) & 0xFFFF) + ip[12:]
    eth = b"\xff" * 6 + MAC + b"\x08\x00"
    return eth + ip + udp


def parse_opts(data):
    i = 240
    found = {}
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
frame = build()
print(f"probe mac {MAC.hex(':')} arch {ARCH} on {IFACE}")
s.send(frame)

seen = {}
end = time.time() + SECS
while time.time() < end:
    try:
        pkt = s.recv(4096)
    except socket.timeout:
        continue
    if pkt[12:14] != b"\x08\x00":
        continue
    ihl = (pkt[14] & 0x0F) * 4
    if pkt[14 + 9] != 17:  # UDP
        continue
    udp = pkt[14 + ihl:]
    sport, dport = struct.unpack("!HH", udp[:4])
    body = udp[8:]
    if dport != 68 or len(body) < 240 or body[4:8] != struct.pack("!I", XID):
        continue
    src = socket.inet_ntoa(pkt[14 + 12:14 + 16])
    siaddr = socket.inet_ntoa(body[20:24])
    yiaddr = socket.inet_ntoa(body[16:20])
    fname = body[108:236].split(b"\0")[0].decode(errors="replace")
    o = parse_opts(body)
    mtype = {1: "DISCOVER", 2: "OFFER", 5: "ACK"}.get(
        o.get(53, b"\0")[0], o.get(53, b"\0")[0])
    key = (src, siaddr, fname, mtype)
    if key in seen:
        continue
    seen[key] = True
    print(f"\nreply from {src} ({mtype})")
    print(f"  siaddr={siaddr} yiaddr={yiaddr} file={fname or '-'}")
    if 54 in o:
        print(f"  server-id={socket.inet_ntoa(o[54])}")
    if 60 in o:
        print(f"  vendor-class={o[60].decode(errors='replace')}")
    if 66 in o:
        print(f"  tftp-server={o[66].decode(errors='replace')}")
    if 67 in o:
        print(f"  bootfile={o[67].decode(errors='replace')}")
    if 43 in o:
        print(f"  option43={o[43].hex()}")
    if 93 in o:
        print(f"  arch-in-reply={struct.unpack('!H', o[93])[:1]}")

if not seen:
    print("NO DHCP REPLIES")
