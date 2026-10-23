#!/usr/bin/env python3
"""Shared service-registry helpers.

The registry is the source of truth. Homepage's services.yaml and layout are
generated from it; do not hand-edit the generated files.
"""
from __future__ import annotations

import datetime as _dt
import os
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "inventory" / "services.yaml"
DISCOVERED = ROOT / "inventory" / "discovered.yaml"
HOMEPAGE_SERVICES = ROOT / "monitoring" / "homepage" / "config" / "services.yaml"
HOMEPAGE_SETTINGS = ROOT / "monitoring" / "homepage" / "config" / "settings.yaml"


def today() -> str:
    return _dt.date.today().isoformat()


def slugify(value: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return out or "service"


def load_registry() -> dict[str, Any]:
    if not REGISTRY.exists():
        return {"version": 1, "groups": {}, "services": []}
    data = yaml.safe_load(REGISTRY.read_text()) or {}
    data.setdefault("version", 1)
    data.setdefault("groups", {})
    data.setdefault("services", [])
    return data


def save_registry(reg: dict[str, Any]) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRY.with_suffix(".yaml.tmp")
    tmp.write_text(
        yaml.safe_dump(reg, sort_keys=False, allow_unicode=True, width=1000)
    )
    os.replace(tmp, REGISTRY)


def ensure_group(reg: dict[str, Any], name: str, columns: int = 4) -> None:
    groups = reg.setdefault("groups", {})
    if name not in groups:
        orders = [int(v.get("order", 0)) for v in groups.values()]
        groups[name] = {
            "order": (max(orders) + 10) if orders else 10,
            "columns": columns,
            "style": "row",
        }


def upsert_service(reg: dict[str, Any], data: dict[str, Any], *, added_by: str = "agent") -> dict[str, Any]:
    """Create/update a service. Returns the stored entry."""
    sid = data.get("id") or slugify(data.get("name", ""))
    data = {k: v for k, v in data.items() if v is not None}
    data["id"] = sid
    ensure_group(reg, data.get("group") or "Services")

    services = reg.setdefault("services", [])
    current = next((s for s in services if s.get("id") == sid), None)
    now = today()
    if current is None:
        current = {
            "id": sid,
            "added_at": now,
            "added_by": added_by,
        }
        services.append(current)

    for key, value in data.items():
        if key in ("added_at", "added_by") and current.get("added_at"):
            continue
        current[key] = value
    current["updated_at"] = now

    if data.get("status") == "active" and not current.get("href"):
        raise ValueError(f"service {sid}: active services need href/url")

    # Keep a Docker source useful to Homepage's native Docker integration while
    # still retaining the source block for discovery/ownership.
    src = current.get("source") or {}
    if src.get("kind") == "docker":
        current.setdefault("docker_server", src.get("host"))
        current.setdefault("docker_container", src.get("ref"))

    return current


def _homepage_props(service: dict[str, Any]) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for key in ("icon", "description", "href"):
        if service.get(key):
            props[key] = service[key]
    if service.get("docker_server"):
        props["server"] = service["docker_server"]
    if service.get("docker_container"):
        props["container"] = service["docker_container"]
    if service.get("widget"):
        props["widget"] = service["widget"]
    return props


def render_homepage(reg: dict[str, Any]) -> tuple[str, str]:
    groups = reg.get("groups") or {}
    group_order = sorted(
        groups.items(), key=lambda kv: (int(kv[1].get("order", 9999)), kv[0])
    )
    services = reg.get("services") or []
    out: list[dict[str, Any]] = []

    for group, meta in group_order:
        items = []
        for service in services:
            if service.get("group") != group:
                continue
            if service.get("status", "active") != "active":
                continue
            if not service.get("href"):
                # Pending entries are intentionally not rendered.
                continue
            items.append({service["name"]: _homepage_props(service)})
        if items:
            out.append({group: items})

    services_text = yaml.safe_dump(
        out, sort_keys=False, allow_unicode=True, width=1000
    )

    settings: dict[str, Any] = {}
    if HOMEPAGE_SETTINGS.exists():
        settings = yaml.safe_load(HOMEPAGE_SETTINGS.read_text()) or {}
    settings["layout"] = {
        group: {
            "style": meta.get("style", "row"),
            "columns": int(meta.get("columns", 4)),
        }
        for group, meta in group_order
    }
    settings_text = yaml.safe_dump(
        settings, sort_keys=False, allow_unicode=True, width=1000
    )
    return services_text, settings_text


def write_homepage(reg: dict[str, Any]) -> None:
    services_text, settings_text = render_homepage(reg)
    HOMEPAGE_SERVICES.write_text(services_text)
    HOMEPAGE_SETTINGS.write_text(settings_text)


def check_homepage(reg: dict[str, Any]) -> list[str]:
    services_text, settings_text = render_homepage(reg)
    problems = []
    if not HOMEPAGE_SERVICES.exists() or HOMEPAGE_SERVICES.read_text() != services_text:
        problems.append(str(HOMEPAGE_SERVICES))
    if not HOMEPAGE_SETTINGS.exists() or HOMEPAGE_SETTINGS.read_text() != settings_text:
        problems.append(str(HOMEPAGE_SETTINGS))
    return problems
