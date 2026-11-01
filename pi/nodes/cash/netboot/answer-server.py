#!/usr/bin/env python3
"""PVE auto-install answer server.

The Proxmox installer POSTs JSON describing the machine that is being
installed. We answer with the answer file that matches it:

    <ANSWERS_DIR>/<mac>.toml        e.g. bc:24:11:ab:12:21.toml
    <ANSWERS_DIR>/<mac-dashed>.toml e.g. bc-24-11-ab-12-21.toml
    <ANSWERS_DIR>/default.toml      fallback

If nothing matches, the response is 404 and the installer drops to a shell
instead of guessing which disk to wipe.

Managed in https://github.com/mjbeatty89/vps-config:
  pi/nodes/cash/netboot/answer-server.py
"""

import json
import os
import pathlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ANSWERS = pathlib.Path(os.environ.get("ANSWERS_DIR", "/srv/answers"))
PORT = int(os.environ.get("PORT", "8091"))


def pick(payload):
    """Return the answer file for this machine, or None."""
    for nic in payload.get("network_interfaces") or []:
        mac = (nic or {}).get("mac")
        if not mac:
            continue
        mac = mac.lower()
        for name in (f"{mac}.toml", f"{mac.replace(':', '-')}.toml"):
            candidate = ANSWERS / name
            if candidate.is_file():
                return candidate
    fallback = ANSWERS / "default.toml"
    return fallback if fallback.is_file() else None


class Handler(BaseHTTPRequestHandler):
    server_version = "pve-answers/1"

    def do_POST(self):  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            payload = {}

        answer = pick(payload)
        macs = [
            (nic or {}).get("mac")
            for nic in (payload.get("network_interfaces") or [])
        ]
        print(
            f"[answer] {self.client_address[0]} macs={macs} -> "
            f"{answer.name if answer else 'NOT FOUND'}",
            flush=True,
        )

        if answer is None:
            self.send_error(404, "no answer file for this machine")
            return

        body = answer.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 - http.server API
        body = b"pve-answers up\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # keep the journal quiet; do_POST already logs one line


if __name__ == "__main__":
    ANSWERS.mkdir(parents=True, exist_ok=True)
    print(f"pve-answers listening on :{PORT} (answers in {ANSWERS})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
