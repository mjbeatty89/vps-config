#!/usr/bin/env python3
"""Propose service-registry entries from Docker labels and Proxmox notes.

This is discovery, not blind inventory: a container/VM must opt in with
homepage labels/notes. By default proposals are written to
inventory/discovered.yaml; --apply merges them through the registry.

Docker labels:
  homepage.enable=true
  homepage.name=Grafana
  homepage.href=https://oracle.manee-frog.ts.net:3002
  homepage.group=Monitoring
  homepage.icon=grafana
  homepage.description=Growth dashboards
  homepage.health=http://grafana:3000/login
  homepage.tailnet=true
  homepage.tags=monitoring,tailnet

Proxmox VM/LXC notes (one per line):
  homepage.enable=true
  homepage.url=https://ai-server.manee-frog.ts.net:9443
  homepage.group=AI
  homepage.icon=omniroute
  homepage.description=OmniRoute gateway

Usage:
  scripts/discover-services.py \
    --host pve=root@10.1.30.13 \
    --host cash=root@10.1.30.8 \
    --host ai-server=root@10.1.30.9 \
    --host unraid=root@10.1.30.16

  scripts/discover-services.py ... --apply
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from service_registry import (  # noqa: E402
    DISCOVERED,
    load_registry,
    save_registry,
    slugify,
    upsert_service,
    write_homepage,
)


def ssh(host: str, command: str, timeout: int = 20) -> str | None:
    try:
        p = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
             "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
             host, command],
            capture_output=True, text=True, timeout=timeout,
        )
    except Exception:
        return None
    if p.returncode != 0:
        return None
    return p.stdout


def parse_hosts(values: list[str]) -> dict[str, str]:
    out = {}
    for value in values:
        if "=" not in value:
            raise SystemExit("--host must be NAME=SSH_TARGET")
        name, target = value.split("=", 1)
        out[name] = target
    return out


def parse_base_urls(values: list[str]) -> dict[str, str]:
    out = {}
    for value in values:
        if "=" not in value:
            raise SystemExit("--base-url must be NAME=URL")
        name, url = value.split("=", 1)
        out[name] = url.rstrip("/")
    return out


def parse_kv(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lower()
        if key.startswith("homepage."):
            out[key[len("homepage."):]] = value.strip()
    return out


def docker_proposals(name: str, target: str, base_url: str | None) -> list[dict[str, Any]]:
    names = ssh(target, "docker ps --format '{{.Names}}'")
    if not names:
        return []
    proposals = []
    for container in [x.strip() for x in names.splitlines() if x.strip()]:
        raw = ssh(target, f"docker inspect --format '{{{{json .Config.Labels}}}}' {shlex.quote(container)}")
        if not raw:
            continue
        try:
            labels = json.loads(raw) or {}
        except Exception:
            continue
        if not isinstance(labels, dict):
            continue
        labels = {str(k).lower(): str(v) for k, v in labels.items()}
        hp = {k[len("homepage."):]: v for k, v in labels.items() if k.startswith("homepage.")}
        if not hp or hp.get("enable", "true").lower() in ("0", "false", "no", "off"):
            continue
        href = hp.get("href") or hp.get("url")
        if not href and base_url and hp.get("port"):
            href = f"{base_url}:{hp['port']}"
        display = hp.get("name") or container
        sid = hp.get("id") or f"{name}-{slugify(display)}"
        group = hp.get("group") or "Docker"
        proposal = {
            "id": sid,
            "name": display,
            "group": group,
            "href": href,
            "icon": hp.get("icon"),
            "description": hp.get("description"),
            "status": "active" if href else "pending",
            "source": {"host": name, "kind": "docker", "ref": container},
            "owner": hp.get("owner", "mjb"),
            "added_by": "discover",
            "tags": sorted({x.strip() for x in hp.get("tags", "").split(",") if x.strip()}),
        }
        if hp.get("health"):
            proposal["widget"] = {"type": "siteMonitor", "url": hp["health"]}
        if hp.get("tailnet", "").lower() in ("1", "true", "yes"):
            proposal.setdefault("tags", []).append("tailnet")
        proposals.append({k: v for k, v in proposal.items() if v not in (None, "", [])})
    return proposals


def _json_tail(text: str | None) -> Any:
    if not text:
        return None
    text = text.strip()
    for start in (0, text.find("["), text.find("{")):
        if start < 0:
            continue
        try:
            return json.loads(text[start:])
        except Exception:
            continue
    return None


def proxmox_proposals(name: str, target: str, base_url: str | None) -> list[dict[str, Any]]:
    if not ssh(target, "command -v pvesh >/dev/null && echo yes"):
        return []
    resources = _json_tail(ssh(target, "pvesh get /cluster/resources --type vm --output-format json", timeout=30))
    if not isinstance(resources, list):
        return []
    proposals = []
    for res in resources:
        if not isinstance(res, dict):
            continue
        node = res.get("node")
        kind = res.get("type")
        vmid = res.get("vmid") or str(res.get("id", "")).split("/")[-1]
        if not (node and kind in ("lxc", "qemu") and vmid):
            continue
        cfg = _json_tail(ssh(target, f"pvesh get /nodes/{shlex.quote(str(node))}/{kind}/{shlex.quote(str(vmid))}/config --output-format json", timeout=20))
        if not isinstance(cfg, dict):
            continue
        hp = parse_kv(str(cfg.get("notes") or ""))
        tags = cfg.get("tags") or ""
        if isinstance(tags, list):
            tags = ",".join(str(x) for x in tags)
        if "homepage" in str(tags).lower() and "url" not in hp and "href" not in hp:
            hp.setdefault("enable", "true")
        if not hp or hp.get("enable", "true").lower() in ("0", "false", "no", "off"):
            continue
        href = hp.get("url") or hp.get("href")
        if not href and base_url and hp.get("port"):
            href = f"{base_url}:{hp['port']}"
        display = hp.get("name") or res.get("name") or f"{kind}-{vmid}"
        sid = hp.get("id") or f"{name}-{slugify(display)}"
        proposal = {
            "id": sid,
            "name": display,
            "group": hp.get("group") or "Proxmox",
            "href": href,
            "icon": hp.get("icon"),
            "description": hp.get("description") or f"{kind.upper()} {vmid} on {node}",
            "status": "active" if href else "pending",
            "source": {"host": name, "kind": kind, "ref": str(vmid)},
            "owner": hp.get("owner", "mjb"),
            "added_by": "discover",
            "tags": sorted({x.strip() for x in (hp.get("tags") or tags).split(",") if x.strip()}),
        }
        if hp.get("health"):
            proposal["widget"] = {"type": "siteMonitor", "url": hp["health"]}
        proposals.append({k: v for k, v in proposal.items() if v not in (None, "", [])})
    return proposals


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", action="append", required=True, help="NAME=SSH_TARGET")
    p.add_argument("--base-url", action="append", default=[], help="NAME=URL")
    p.add_argument("--apply", action="store_true", help="merge proposals into registry")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    hosts = parse_hosts(args.host)
    bases = parse_base_urls(args.base_url)
    proposals: list[dict[str, Any]] = []
    for name, target in hosts.items():
        proposals.extend(docker_proposals(name, target, bases.get(name)))
        proposals.extend(proxmox_proposals(name, target, bases.get(name)))

    # De-duplicate by id; later hosts win only for identical ids.
    dedup: dict[str, dict[str, Any]] = {}
    for proposal in proposals:
        dedup[proposal["id"]] = proposal
    proposals = list(dedup.values())

    doc = {
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "hosts": hosts,
        "proposals": proposals,
    }
    DISCOVERED.parent.mkdir(parents=True, exist_ok=True)
    DISCOVERED.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=1000))

    print(f"{len(proposals)} opt-in service proposal(s) -> {DISCOVERED}")
    for x in proposals:
        print(f"  {x['status']:7} {x['id']:30} {x.get('href', '(no url)')}  ({x['source']['host']})")

    if args.apply and not args.dry_run:
        reg = load_registry()
        for proposal in proposals:
            upsert_service(reg, proposal, added_by="discover")
        save_registry(reg)
        write_homepage(reg)
        print(f"applied {len(proposals)} proposal(s) to inventory/services.yaml")
    elif args.apply:
        print("dry-run: not applying")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
