"""Strict replay of retained Apex build-manifest evidence."""

from __future__ import annotations

import json

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.provenance import BuildManifest


def _strict_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be integer")
    return value


def load_build_manifest(
    artifact_id: str,
    *,
    store: ArtifactStore,
    expected_runtime_digest: str | None = None,
    verify_members: bool = True,
) -> BuildManifest:
    """Replay the CI build-manifest envelope without conflating file and semantic IDs."""

    try:
        raw = json.loads(store.read_bytes(artifact_id).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("build manifest artifact is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError("build manifest artifact must be object")
    if raw.get("schema_name") != "apex-build-manifest":
        raise ValueError("not an Apex build manifest")
    if _strict_int(raw.get("schema_version"), label="build manifest schema_version") != 1:
        raise ValueError("unsupported build manifest schema")
    payload = raw.get("payload")
    declared = raw.get("build_manifest_id")
    if not isinstance(payload, dict) or not isinstance(declared, str):
        raise ValueError("build manifest payload/semantic identity is invalid")
    action_rows = payload.get("action_pins", [])
    if not isinstance(action_rows, list):
        raise ValueError("build manifest action_pins must be array")
    action_pins: list[tuple[str, str]] = []
    for row in action_rows:
        if not isinstance(row, list) or len(row) != 2:
            raise ValueError("build manifest action pin must be [name, sha]")
        action_pins.append((str(row[0]), str(row[1])))
    manifest = BuildManifest(
        source_sha=str(payload.get("source_sha") or ""),
        dependency_lock_digest=str(payload.get("dependency_lock_digest") or ""),
        runtime_digest=str(payload.get("runtime_digest") or ""),
        base_image_digest=str(payload.get("base_image_digest") or ""),
        builder_identity=str(payload.get("builder_identity") or ""),
        built_at=str(payload.get("built_at") or ""),
        sbom_artifact_id=str(payload.get("sbom_artifact_id") or ""),
        provenance_artifact_id=str(payload.get("provenance_artifact_id") or ""),
        action_pins=tuple(action_pins),
        schema_name=str(payload.get("schema_name") or ""),
        schema_version=_strict_int(payload.get("schema_version"), label="build payload schema_version"),
    )
    if manifest.semantic_payload() != payload or manifest.build_manifest_id != declared:
        raise ValueError("build manifest semantic identity mismatch")
    if expected_runtime_digest is not None and manifest.runtime_digest != str(expected_runtime_digest):
        raise ValueError("build manifest runtime digest mismatch")
    if verify_members:
        for label, member_id in (
            ("dependency lock", manifest.dependency_lock_digest),
            ("SBOM", manifest.sbom_artifact_id),
            ("provenance", manifest.provenance_artifact_id),
        ):
            if not store.verify(member_id):
                raise ValueError(f"build manifest {label} artifact is missing/corrupt")
    return manifest
