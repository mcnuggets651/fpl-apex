"""Load and replay the explicit V2 post-event outcome truth registry."""

from __future__ import annotations

from pathlib import Path

import yaml

from apex_fpl.core.outcome_truth import (
    OutcomeTarget,
    OutcomeTruthAuthority,
    OutcomeTruthRegistry,
    TruthAuthorityStatus,
)


def _registry_from_raw(raw: object) -> OutcomeTruthRegistry:
    if not isinstance(raw, dict) or int(raw.get("schema_version", -1)) != 1:
        raise ValueError("outcome truth registry requires schema_version 1")
    rows = raw.get("authorities")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("outcome truth authorities must be an array of objects")
    authorities = tuple(
        OutcomeTruthAuthority(
            target=OutcomeTarget(str(row.get("target") or "")),
            status=TruthAuthorityStatus(str(row.get("status") or "")),
            source_id=None if row.get("source_id") is None else str(row["source_id"]),
            capability=None if row.get("capability") is None else str(row["capability"]),
            source_reference=(
                None if row.get("source_reference") is None else str(row["source_reference"])
            ),
            field_contract=(
                None if row.get("field_contract") is None else str(row["field_contract"])
            ),
            rationale=str(row.get("rationale") or ""),
        )
        for row in rows
    )
    return OutcomeTruthRegistry(authorities)


def load_outcome_truth_registry_bytes(content: bytes) -> OutcomeTruthRegistry:
    if not isinstance(content, bytes):
        raise TypeError("outcome truth registry content must be bytes")
    try:
        raw = yaml.safe_load(content.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError("outcome truth registry is not valid UTF-8 YAML") from exc
    return _registry_from_raw(raw)


def load_outcome_truth_registry(path: str | Path) -> OutcomeTruthRegistry:
    return load_outcome_truth_registry_bytes(Path(path).read_bytes())
