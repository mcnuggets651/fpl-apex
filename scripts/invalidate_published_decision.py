#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from apex_fpl.services.publication import invalidate_published_decision


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--output-dir", default="data/generated")
    args = parser.parse_args()

    invalidate_published_decision(
        Path(args.output_dir),
        source_name=args.source,
        reason=args.reason,
    )
    print(f"Invalidated canonical decision because {args.source} changed")


if __name__ == "__main__":
    main()
