#!/usr/bin/env python3
"""Generate a deterministic SPDX 2.3 application SBOM from the frozen runtime lock."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path


BASE_IMAGE = (
    "python:3.12.14-slim-bookworm@"
    "sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134"
)


def _packages(lock: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw in lock.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            raise ValueError(f"unfrozen lock line: {line}")
        name, version = line.split("==", 1)
        spdx_id = "SPDXRef-Python-" + "".join(ch if ch.isalnum() else "-" for ch in name)
        rows.append(
            {
                "SPDXID": spdx_id,
                "name": name,
                "versionInfo": version,
                "downloadLocation": f"https://pypi.org/project/{name}/{version}/",
                "filesAnalyzed": False,
            }
        )
    return sorted(rows, key=lambda row: str(row["name"]).casefold())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", default="requirements.runtime.lock")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    lock = Path(args.lock)
    lock_digest = sha256(lock.read_bytes()).hexdigest()
    packages = _packages(lock)
    packages.insert(
        0,
        {
            "SPDXID": "SPDXRef-BaseImage",
            "name": "python-3.12.14-slim-bookworm",
            "versionInfo": "3.12.14",
            "downloadLocation": "https://hub.docker.com/_/python",
            "filesAnalyzed": False,
            "externalRefs": [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": f"pkg:docker/python@{BASE_IMAGE.split('@', 1)[1]}",
                }
            ],
        },
    )
    document = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "apex-core-runtime",
        "documentNamespace": f"https://apex-fpl.local/sbom/sha256-{lock_digest}",
        "creationInfo": {
            "creators": ["Tool: apex-fpl/scripts/generate_spdx_sbom.py"],
            "created": "2026-08-23T00:00:00Z",
        },
        "packages": packages,
        "annotations": [
            {
                "annotationType": "OTHER",
                "annotator": "Tool: apex-fpl/scripts/generate_spdx_sbom.py",
                "annotationDate": "2026-08-23T00:00:00Z",
                "comment": (
                    "Application dependency SBOM derived from the frozen Python runtime lock; "
                    "base OCI image is content pinned separately."
                ),
            }
        ],
    }
    Path(args.output).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
