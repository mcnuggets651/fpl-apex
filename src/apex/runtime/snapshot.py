from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from apex.domain.models import OfficialSnapshot, ProjectionSurface


@dataclass(frozen=True)
class FrozenInputSnapshot:
    schema_version: int
    snapshot_id: str
    official: OfficialSnapshot
    providers: dict[str, ProjectionSurface]
    evidence: dict[str, Any]
    enrichment: dict[str, Any]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def freeze_input_snapshot(
    *,
    official: OfficialSnapshot,
    providers: dict[str, ProjectionSurface],
    evidence: dict[str, Any] | None = None,
    enrichment: dict[str, Any] | None = None,
    destination: str | Path,
) -> FrozenInputSnapshot:
    payload = {
        "schema_version": 1,
        "official": asdict(official),
        "providers": {key: asdict(value) for key, value in sorted(providers.items())},
        "evidence": evidence or {},
        "enrichment": enrichment or {},
    }
    snapshot_id = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    frozen = FrozenInputSnapshot(
        schema_version=1,
        snapshot_id=snapshot_id,
        official=official,
        providers=dict(providers),
        evidence=evidence or {},
        enrichment=enrichment or {},
    )
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {**payload, "snapshot_id": snapshot_id},
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    return frozen
