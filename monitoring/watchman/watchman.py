#!/usr/bin/env python3
"""
watchman — a small persistent monitoring agent for the aadd VPS gateway.

Responsibilities
  * Poll Prometheus every POLL_SECONDS for down targets / failing probes.
  * Alert to Telegram on state transitions (up->down, down->up), with cooldown.
  * Answer Telegram commands:  /status  /problems  /host  /help
  * Keep state in STATE_FILE so restarts don't re-alert.

Stdlib only. Configure via environment (see watchman.env.example).
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

PROM = os.environ.get("PROMETHEUS_URL", "http://127.0.0.1:9090")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_API", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
POLL_SECONDS = int(os.environ.get("WATCHMAN_POLL_SECONDS", "60"))
STATE_FILE = os.environ.get("WATCHMAN_STATE", "/var/lib/watchman/state.json")
REALERT_SECONDS = int(os.environ.get("WATCHMAN_REALERT_SECONDS", str(24 * 3600)))
FAILURE_WINDOW = os.environ.get("WATCHMAN_FAILURE_WINDOW", "15m")
FAILURE_REASON = f"down for {FAILURE_WINDOW}"
# The PVE exporter is a noisy secondary telemetry path; the node-exporter jobs
# already monitor PVE host reachability. Require two hours before paging on an
# exporter-only failure so API latency cannot generate routine notifications.
JOB_WINDOWS = {"pve": "2h", "pvevcm": "2h"}
# When false, watchman only SENDS alerts (no getUpdates polling), so it can share
# a bot token with another agent that owns the polling loop.
POLL_TELEGRAM = os.environ.get("WATCHMAN_POLL_TELEGRAM", "true").lower() in ("1", "true", "yes", "on")


# ── helpers ────────────────────────────────────────────────────────────────
def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}", flush=True)


def prom_query(expr: str):
    url = f"{PROM}/api/v1/query?" + urllib.parse.urlencode({"query": expr})
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.load(r).get("data", {}).get("result", [])
    except Exception as e:  # noqa: BLE001
        log(f"prom query failed: {e}")
        return []


def scalar(expr: str, default: float = 0.0) -> float:
    res = prom_query(expr)
    if not res:
        return default
    try:
        return float(res[0]["value"][1])
    except Exception:  # noqa: BLE001
        return default


def tg(method: str, **params):
    if not BOT_TOKEN:
        return None
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=15) as r:
            return json.load(r)
    except Exception as e:  # noqa: BLE001
        log(f"telegram {method} failed: {e}")
        return None


def send(text: str) -> None:
    if not CHAT_ID:
        log(f"(no chat id) would send: {text}")
        return
    tg("sendMessage", chat_id=CHAT_ID, text=text, disable_web_page_preview="true")


# ── state ──────────────────────────────────────────────────────────────────
def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {"down": {}, "last_alert": {}}


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_FILE)


# ── checks ─────────────────────────────────────────────────────────────────
def current_problems() -> dict[str, str]:
    """Return only sustained failures; use stricter windows for noisy jobs."""
    problems: dict[str, str] = {}
    excluded = "|".join(JOB_WINDOWS)
    for r in prom_query(
        f'max_over_time(up{{job!~"{excluded}"}}[{FAILURE_WINDOW}]) == 0'
    ):
        m = r["metric"]
        problems[f"{m.get('job','?')}:{m.get('instance','?')}"] = FAILURE_REASON
    for job, window in JOB_WINDOWS.items():
        for r in prom_query(f'max_over_time(up{{job="{job}"}}[{window}]) == 0'):
            m = r["metric"]
            problems[f"{job}:{m.get('instance','?')}"] = f"down for {window}"
    for r in prom_query(
        f'max_over_time(probe_success[{FAILURE_WINDOW}]) == 0'
    ):
        m = r["metric"]
        problems[f"probe:{m.get('instance','?')}"] = f"probe failing for {FAILURE_WINDOW}"
    return problems


def host_summary() -> str:
    cpu = scalar('100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)')
    mem = scalar("(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100")
    dsk = scalar('(1 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100')
    load = scalar("node_load1")
    up = scalar("count(up == 1)")
    total = up + scalar("count(up == 0)")
    return (
        f"Host: CPU {cpu:.0f}% · MEM {mem:.0f}% · DISK / {dsk:.0f}% · load {load:.2f}\n"
        f"Targets: {up:.0f}/{total:.0f} up"
    )


def check_cycle(state: dict) -> None:
    problems = current_problems()
    prev = state.get("down", {})
    last_alert = state.get("last_alert", {})
    now = time.time()

    for target, reason in problems.items():
        was = prev.get(target)
        due = now - last_alert.get(target, 0) > REALERT_SECONDS
        if was is None or was != reason:
            send(f"🔴 DOWN  {target}\nreason: {reason}")
            last_alert[target] = now
        elif due:
            send(f"🔴 STILL DOWN  {target}\nreason: {reason}")
            last_alert[target] = now

    for target in list(prev.keys()):
        if target not in problems:
            send(f"🟢 RECOVERED  {target}")

    state["down"] = problems
    state["last_alert"] = last_alert
    save_state(state)


# ── telegram command loop ──────────────────────────────────────────────────
def handle_command(text: str) -> None:
    cmd = text.strip().split()[0].split("@")[0].lower() if text.strip() else ""
    if cmd in ("/start", "/help"):
        send(
            "watchman online.\n"
            "/status — host + target summary\n"
            "/problems — list failing targets\n"
            "/host — host resource detail\n"
            "Alerts arrive automatically on up/down transitions."
        )
    elif cmd == "/status":
        probs = current_problems()
        line = "✅ all clear" if not probs else "🔴 " + ", ".join(probs)
        send(f"{host_summary()}\n{line}")
    elif cmd == "/problems":
        probs = current_problems()
        send("No problems." if not probs else "\n".join(f"🔴 {k} — {v}" for k, v in probs.items()))
    elif cmd == "/host":
        send(host_summary())


def poll_telegram(offset: int | None) -> int | None:
    if not BOT_TOKEN:
        return offset
    params = {"timeout": 25}
    if offset is not None:
        params["offset"] = offset
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=35) as r:
            data = json.load(r)
    except Exception:  # noqa: BLE001
        return offset
    for u in data.get("result", []):
        offset = u["update_id"] + 1
        msg = u.get("message") or {}
        if str(msg.get("chat", {}).get("id")) == CHAT_ID and msg.get("text"):
            handle_command(msg["text"])
    return offset


def main() -> None:
    log(f"watchman starting (prom={PROM}, chat={'set' if CHAT_ID else 'unset'}, poll={POLL_TELEGRAM})")
    state = load_state()
    # Startup is silent: restarting the service must not itself page Telegram.
    offset: int | None = None
    last_check = 0.0
    while True:
        if POLL_TELEGRAM:
            offset = poll_telegram(offset)  # blocks up to ~25s
        else:
            time.sleep(5)
        if time.time() - last_check >= POLL_SECONDS:
            try:
                check_cycle(state)
            except Exception as e:  # noqa: BLE001
                log(f"check cycle error: {e}")
            last_check = time.time()


if __name__ == "__main__":
    main()
