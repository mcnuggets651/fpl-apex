"""Requirements traceability registry and orphan detection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from apex_fpl.core.canonical import canonical_sha256
from apex_fpl.control.proof_registry import ProofRegistry


@dataclass(frozen=True, slots=True)
class Requirement:
    requirement_id: str
    requirement: str
    critical: bool
    invariants: tuple[str, ...]
    implementation: tuple[str, ...]
    tests: tuple[str, ...]
    proof_obligations: tuple[str, ...]

    @property
    def orphaned(self) -> bool:
        if not self.critical:
            return False
        return not all(
            (
                self.invariants,
                self.implementation,
                self.tests,
                self.proof_obligations,
            )
        )


@dataclass(frozen=True, slots=True)
class RequirementsTraceabilityMatrix:
    requirements: tuple[Requirement, ...]
    digest: str

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        proof_registry: ProofRegistry,
    ) -> "RequirementsTraceabilityMatrix":
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if payload.get("schema_version") != 1:
            raise ValueError("unsupported requirements registry schema_version")
        rows = payload.get("requirements")
        if not isinstance(rows, list) or not rows:
            raise ValueError("requirements registry must contain requirements")
        requirements = tuple(_parse_requirement(row) for row in rows)
        ids = [item.requirement_id for item in requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("requirements registry contains duplicate requirement_id")

        proof_ids = set(proof_registry.by_id())
        for item in requirements:
            if item.orphaned:
                raise ValueError(f"critical requirement is orphaned: {item.requirement_id}")
            unknown = sorted(set(item.proof_obligations) - proof_ids)
            if unknown:
                raise ValueError(
                    f"{item.requirement_id}: unknown proof obligations: {unknown}"
                )
        return cls(requirements=requirements, digest=canonical_sha256(payload))

    def critical_orphans(self) -> tuple[str, ...]:
        return tuple(item.requirement_id for item in self.requirements if item.orphaned)


def _string_tuple(row: dict[str, Any], key: str) -> tuple[str, ...]:
    value = row.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"requirement {key} must be a string list")
    return tuple(value)


def _parse_requirement(value: object) -> Requirement:
    if not isinstance(value, dict):
        raise ValueError("requirement row must be an object")
    row: dict[str, Any] = value
    try:
        return Requirement(
            requirement_id=str(row["requirement_id"]),
            requirement=str(row["requirement"]),
            critical=bool(row["critical"]),
            invariants=_string_tuple(row, "invariants"),
            implementation=_string_tuple(row, "implementation"),
            tests=_string_tuple(row, "tests"),
            proof_obligations=_string_tuple(row, "proof_obligations"),
        )
    except KeyError as exc:
        raise ValueError(f"requirement missing field: {exc.args[0]}") from exc
