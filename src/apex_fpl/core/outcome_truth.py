"""Post-event truth authority contracts used by calibration and replay.

Experiments must not silently choose different ground-truth providers. Unknown/unverified
authority remains explicit rather than being filled by a convenient dataset.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse

from .canonical import canonical_sha256
from .ids import OutcomeTruthRegistryId


class OutcomeTarget(str, Enum):
    FPL_POINTS = "FPL_POINTS"
    MINUTES = "MINUTES"
    START = "START"
    LINEUP = "LINEUP"
    PRICE = "PRICE"
    GOAL = "GOAL"
    ASSIST = "ASSIST"
    UNDERLYING_XG = "UNDERLYING_XG"
    UNDERLYING_XA = "UNDERLYING_XA"
    DEFENSIVE_CONTRIBUTION = "DEFENSIVE_CONTRIBUTION"


class TruthAuthorityStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class OutcomeTruthAuthority:
    target: OutcomeTarget
    status: TruthAuthorityStatus
    source_id: str | None
    capability: str | None
    source_reference: str | None
    field_contract: str | None
    rationale: str

    def __post_init__(self) -> None:
        rationale = str(self.rationale).strip()
        if not rationale:
            raise ValueError("outcome truth authority requires rationale")
        object.__setattr__(self, "rationale", rationale)
        if self.status is TruthAuthorityStatus.VERIFIED:
            source_id = str(self.source_id or "").strip()
            capability = str(self.capability or "").strip()
            reference = str(self.source_reference or "").strip()
            field_contract = str(self.field_contract or "").strip()
            parsed = urlparse(reference)
            if not source_id or not capability or not field_contract:
                raise ValueError("verified truth authority requires source/capability/field contract")
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("verified truth authority requires absolute source reference")
            object.__setattr__(self, "source_id", source_id)
            object.__setattr__(self, "capability", capability)
            object.__setattr__(self, "source_reference", reference)
            object.__setattr__(self, "field_contract", field_contract)
        else:
            if any(
                value is not None
                for value in (
                    self.source_id,
                    self.capability,
                    self.source_reference,
                    self.field_contract,
                )
            ):
                raise ValueError("unresolved truth authority cannot pretend to name an authority")

    def semantic_payload(self) -> dict[str, object]:
        return {
            "target": self.target.value,
            "status": self.status.value,
            "source_id": self.source_id,
            "capability": self.capability,
            "source_reference": self.source_reference,
            "field_contract": self.field_contract,
            "rationale": self.rationale,
        }


@dataclass(frozen=True, slots=True)
class OutcomeTruthRegistry:
    authorities: tuple[OutcomeTruthAuthority, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported OutcomeTruthRegistry schema_version")
        authorities = tuple(sorted(self.authorities, key=lambda row: row.target.value))
        targets = [row.target for row in authorities]
        if len(targets) != len(set(targets)):
            raise ValueError("outcome truth registry has duplicate target authority")
        missing = set(OutcomeTarget) - set(targets)
        if missing:
            raise ValueError(
                "outcome truth registry must explicitly resolve or mark unresolved every target: "
                + ", ".join(sorted(item.value for item in missing))
            )
        object.__setattr__(self, "authorities", authorities)

    @property
    def registry_id(self) -> str:
        return canonical_sha256(
            {
                "schema_name": "apex-outcome-truth-registry",
                "schema_version": self.schema_version,
                "authorities": [row.semantic_payload() for row in self.authorities],
            }
        )

    @property
    def truth_registry_id(self) -> OutcomeTruthRegistryId:
        return OutcomeTruthRegistryId(self.registry_id)

    def authority_for(self, target: OutcomeTarget) -> OutcomeTruthAuthority:
        return next(row for row in self.authorities if row.target is target)
