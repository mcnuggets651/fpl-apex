#!/usr/bin/env python3
"""Acquire the manager-neutral official FPL GlobalWorld into ArtifactStore."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from apex_fpl.acquisition import RequestsTransport, SystemClock, acquire_official_global_world
from apex_fpl.control.artifact_store import FileSystemArtifactStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freshness-seconds", type=int, default=1800)
    args = parser.parse_args()

    store = FileSystemArtifactStore(args.artifact_root)
    sealed = acquire_official_global_world(
        season=args.season,
        transport=RequestsTransport(),
        clock=SystemClock(),
        store=store,
        freshness_seconds=args.freshness_seconds,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(sealed.as_dict(), indent=2) + "\n", encoding="utf-8")
    print(json.dumps(sealed.as_dict(), indent=2))


if __name__ == "__main__":
    main()
