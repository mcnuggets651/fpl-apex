#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from apex.runtime.provenance import write_reproducibility_artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description="Build sealed Apex V2 provenance and CycloneDX SBOM")
    parser.add_argument("--engine-sha", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/v2"))
    parser.add_argument("--lock", type=Path, default=Path("requirements-v2.lock"))
    parser.add_argument("--workflow", type=Path, default=Path(".github/workflows/apex-v2-ci.yml"))
    parser.add_argument("--upstreams", type=Path, default=Path("upstreams.lock.json"))
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    provenance, sbom = write_reproducibility_artifacts(
        root,
        args.output_dir,
        engine_sha=args.engine_sha,
        lock_path=root / args.lock,
        workflow_path=root / args.workflow,
        upstreams_path=root / args.upstreams,
    )
    print(f"wrote {provenance}")
    print(f"wrote {sbom}")


if __name__ == "__main__":
    main()
