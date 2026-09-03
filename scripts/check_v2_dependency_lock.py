#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from apex.runtime.provenance import read_exact_lock, verify_installed_against_lock


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify installed Apex V2 environment against exact lock")
    parser.add_argument("lock", nargs="?", type=Path, default=Path("requirements-v2.lock"))
    args = parser.parse_args()
    lock = read_exact_lock(args.lock)
    errors = verify_installed_against_lock(lock)
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Apex V2 dependency lock verified: {len(lock)} exact external distributions")


if __name__ == "__main__":
    main()
