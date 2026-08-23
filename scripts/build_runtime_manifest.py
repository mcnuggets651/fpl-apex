#!/usr/bin/env python3
"""Materialise a BuildManifest from externally proven immutable build inputs."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from apex_fpl.control.provenance import BuildManifest


def _digest(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--runtime-digest", required=True)
    parser.add_argument("--builder-identity", required=True)
    parser.add_argument("--built-at", required=True)
    parser.add_argument("--sbom", required=True)
    parser.add_argument("--provenance", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    manifest = BuildManifest(
        source_sha=args.source_sha,
        dependency_lock_digest=_digest(Path("requirements.runtime.lock")),
        runtime_digest=args.runtime_digest,
        base_image_digest=(
            "sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134"
        ),
        builder_identity=args.builder_identity,
        built_at=args.built_at,
        sbom_artifact_id=_digest(Path(args.sbom)),
        provenance_artifact_id=_digest(Path(args.provenance)),
        action_pins=(
            ("actions/checkout", "11d5960a326750d5838078e36cf38b85af677262"),
            ("actions/setup-python", "a26af69be951a213d495a4c3e4e4022e16d87065"),
            ("actions/cache", "1bd1e32a3bdc45362d1e726936510720a7c30a57"),
            ("actions/upload-artifact", "ea165f8d65b6e75b540449e92b4886f43607fa02"),
        ),
    )
    payload = {**manifest.semantic_payload(), "build_manifest_id": manifest.build_manifest_id}
    Path(args.output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
