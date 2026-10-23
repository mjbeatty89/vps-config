#!/usr/bin/env python3
"""Register/update a homelab web service in inventory/services.yaml.

Examples:
  scripts/register-service.py \
    --name Grafana --url https://oracle.manee-frog.ts.net:3002 \
    --group Monitoring --icon grafana --source-host vps \
    --source-kind docker --source-ref grafana --tag tailnet \
    --health http://grafana:3000/login --added-by opencode

  scripts/register-service.py --name "New App" --group Apps \
    --source-host pve --source-kind lxc --source-ref 120 --pending

After registration the generated Homepage config is refreshed. Do not edit
monitoring/homepage/config/services.yaml by hand.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from service_registry import (  # noqa: E402
    REGISTRY,
    load_registry,
    save_registry,
    slugify,
    upsert_service,
    write_homepage,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--id", help="stable registry id (default: slug of --name)")
    p.add_argument("--name", help="display name")
    p.add_argument("--url", "--href", dest="url", help="browser URL")
    p.add_argument("--group", default="Services", help="Homepage group")
    p.add_argument("--icon", help="Homepage icon name")
    p.add_argument("--description")
    p.add_argument("--health", help="health/status URL for siteMonitor")
    p.add_argument("--widget-json", help="explicit Homepage widget JSON")
    p.add_argument("--source-host", help="vps, pve, pvevcm, cash, ai-server, unraid, ...")
    p.add_argument(
        "--source-kind",
        choices=["manual", "docker", "lxc", "qemu", "systemd", "tailscale", "external"],
        default="manual",
    )
    p.add_argument("--source-ref", help="container name, VMID, unit, etc.")
    p.add_argument("--docker-server", help="Homepage docker integration server")
    p.add_argument("--docker-container", help="Homepage docker integration container")
    p.add_argument("--owner", default="mjb")
    p.add_argument("--added-by", default="agent")
    p.add_argument("--tag", action="append", default=[], help="tag (repeatable)")
    p.add_argument("--pending", action="store_true", help="register without a URL yet")
    p.add_argument("--status", choices=["active", "pending"], help="override status")
    p.add_argument("--no-render", action="store_true", help="do not refresh Homepage")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def main() -> int:
    a = parse_args()
    if not a.name and not a.id:
        raise SystemExit("--name or --id is required")
    if not a.url and not a.pending and a.status != "pending":
        raise SystemExit("--url is required unless --pending is set")

    status = a.status or ("pending" if a.pending or not a.url else "active")
    data = {
        "id": a.id or slugify(a.name or ""),
        "name": a.name,
        "group": a.group,
        "href": a.url,
        "icon": a.icon,
        "description": a.description,
        "status": status,
        "owner": a.owner,
    }
    if a.source_host or a.source_ref or a.source_kind != "manual":
        data["source"] = {
            "host": a.source_host,
            "kind": a.source_kind,
            "ref": a.source_ref,
        }
    if a.docker_server:
        data["docker_server"] = a.docker_server
    if a.docker_container:
        data["docker_container"] = a.docker_container
    if a.tag:
        data["tags"] = sorted(set(a.tag))
    if a.widget_json:
        data["widget"] = json.loads(a.widget_json)
    elif a.health:
        data["widget"] = {"type": "siteMonitor", "url": a.health}

    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    with (REGISTRY.parent / ".services.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        reg = load_registry()
        entry = upsert_service(reg, data, added_by=a.added_by)
        if a.dry_run:
            print(json.dumps(entry, indent=2))
            return 0
        save_registry(reg)
        if not a.no_render:
            write_homepage(reg)

    print(f"{'pending' if entry.get('status') == 'pending' else 'active'} {entry['id']} -> {entry.get('href', '(no url)')}")
    if not a.no_render:
        print("updated monitoring/homepage/config/services.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
