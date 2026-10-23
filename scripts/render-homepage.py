#!/usr/bin/env python3
"""Render Homepage config from inventory/services.yaml.

Usage:
  scripts/render-homepage.py          # write generated config
  scripts/render-homepage.py --check  # CI/deploy drift check
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from service_registry import load_registry, write_homepage, check_homepage  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true", help="exit nonzero if generated files are stale")
    args = p.parse_args()

    reg = load_registry()
    if args.check:
        problems = check_homepage(reg)
        if problems:
            print("Homepage config is stale. Run scripts/render-homepage.py and commit:")
            for path in problems:
                print(f"  - {path}")
            return 1
        print("Homepage config is up to date.")
        return 0

    write_homepage(reg)
    print(f"Rendered {len(reg.get('services', []))} registry entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
