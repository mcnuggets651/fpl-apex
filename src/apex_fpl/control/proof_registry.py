"""Load and validate the machine-readable V2 proof-obligation registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from apex_fpl.core.canonical import canonical_sha256
from apex_fpl.core.proofs import ProofClass, ProofObligation, ReleasePolicy


@dataclass(frozen=True, slots=True)
class ProofRegistry:
    obligations: tuple[ProofObligation, ...]
    digest: str

    @classmethod
    def load(cls, path: str | Path) -> "ProofRegistry":
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if payload.get("schema_version") != 1:
            raise ValueError("unsupported proof registry schema_version")
        rows = payload.get("proof_obligations")
        if not isinstance(rows, list) or not rows:
            raise ValueError("proof registry must contain proof_obligations")

        obligations = tuple(_parse_obligation(row) for row in rows)
        ids = [item.proof_id for item in obligations]
        if len(ids) != len(set(ids)):
            raise ValueError("proof registry contains duplicate proof_id")
        return cls(obligations=obligations, digest=canonical_sha256(payload))

    def by_id(self) -> dict[str, ProofObligation]:
        return {item.proof_id: item for item in self.obligations}


def _strings(row: dict[str, Any], key: str) -> tuple[str, ...]:
    value = row.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be a string list")
    return tuple(value)


def _parse_obligation(value: object) -> ProofObligation:
    if not isinstance(value, dict):
        raise ValueError("proof obligation row must be an object")
    row: dict[str, Any] = value
    try:
        return ProofObligation(
            proof_id=str(row["proof_id"]),
            claim=str(row["claim"]),
            proof_class=ProofClass(str(row["proof_class"])),
            scope=str(row["scope"]),
            required_evidence=_strings(row, "required_evidence"),
            required_tests=_strings(row, "required_tests"),
            failure_consequence=str(row["failure_consequence"]),
            release_policy=ReleasePolicy(str(row["release_policy"])),
            owner=str(row["owner"]),
        )
    except KeyError as exc:
        raise ValueError(f"proof obligation missing field: {exc.args[0]}") from exc
