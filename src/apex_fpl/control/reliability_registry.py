"""Source x claim x horizon x recency reliability registry.

Missing calibration is not an error and never receives a guessed coefficient.  Lookup
returns an explicit UNKNOWN ReliabilityContext until a matching qualification record is
registered and its artifact verifies.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.reliability import ReliabilityContext, ReliabilityQualification


@dataclass(frozen=True, slots=True)
class ReliabilityRegistry:
    contexts: tuple[ReliabilityContext, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported reliability registry schema_version")
        keys: set[tuple[str, str, int, str]] = set()
        for row in self.contexts:
            key = (
                row.source_id,
                row.claim_type,
                row.horizon_gameweeks,
                row.recency_bucket,
            )
            if key in keys:
                raise ValueError(f"duplicate reliability context: {key}")
            keys.add(key)

    def lookup(
        self,
        *,
        source_id: str,
        claim_type: str,
        horizon_gameweeks: int,
        recency_bucket: str,
    ) -> ReliabilityContext:
        for row in self.contexts:
            if (
                row.source_id == source_id
                and row.claim_type == claim_type
                and row.horizon_gameweeks == horizon_gameweeks
                and row.recency_bucket == recency_bucket
            ):
                return row
        return ReliabilityContext(
            source_id=source_id,
            claim_type=claim_type,
            horizon_gameweeks=horizon_gameweeks,
            recency_bucket=recency_bucket,
            qualification=ReliabilityQualification.UNKNOWN,
        )

    def verify_qualified_artifacts(self, store: ArtifactStore) -> None:
        for row in self.contexts:
            if row.qualification is not ReliabilityQualification.QUALIFIED:
                continue
            artifact = row.qualification_artifact_id
            if artifact is None or not store.verify(artifact):
                raise ValueError(
                    "qualified reliability artifact is missing/corrupt for "
                    f"{row.source_id}:{row.claim_type}:{row.horizon_gameweeks}:"
                    f"{row.recency_bucket}"
                )


def load_reliability_registry(path: str | Path) -> ReliabilityRegistry:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or int(raw.get("schema_version", -1)) != 1:
        raise ValueError("reliability registry requires schema_version 1")
    rows = raw.get("contexts", [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("reliability contexts must be an array of objects")
    contexts = tuple(
        ReliabilityContext(
            source_id=str(row.get("source_id") or ""),
            claim_type=str(row.get("claim_type") or ""),
            horizon_gameweeks=int(row.get("horizon_gameweeks", 0)),
            recency_bucket=str(row.get("recency_bucket") or ""),
            qualification=ReliabilityQualification(
                str(row.get("qualification") or "UNKNOWN")
            ),
            reliability_bps=(
                None
                if row.get("reliability_bps") is None
                else int(row["reliability_bps"])
            ),
            sample_count=int(row.get("sample_count", 0)),
            qualification_artifact_id=(
                None
                if row.get("qualification_artifact_id") is None
                else str(row["qualification_artifact_id"])
            ),
        )
        for row in rows
    )
    return ReliabilityRegistry(contexts)
