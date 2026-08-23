"""Typed execution and semantic identifiers for Apex V2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class ApexId:
    """Base value object. Subclasses are intentionally not interchangeable by type."""

    value: str
    kind: ClassVar[str] = "id"

    def __post_init__(self) -> None:
        text = str(self.value).strip()
        if not text:
            raise ValueError(f"{self.kind} cannot be empty")
        if any(char.isspace() for char in text):
            raise ValueError(f"{self.kind} cannot contain whitespace")
        object.__setattr__(self, "value", text)

    def __str__(self) -> str:
        return self.value


class RunId(ApexId):
    kind = "run_id"


class RawCaptureId(ApexId):
    kind = "raw_capture_id"


class GlobalWorldId(ApexId):
    kind = "global_world_id"


class PersonId(ApexId):
    kind = "person_id"


class RuleSetId(ApexId):
    kind = "ruleset_id"


class ManagerStateId(ApexId):
    kind = "manager_state_id"


class DecisionWorldId(ApexId):
    kind = "decision_world_id"


class ForecastId(ApexId):
    kind = "forecast_id"


class ScenarioSetId(ApexId):
    kind = "scenario_set_id"


class DecisionInputId(ApexId):
    kind = "decision_input_id"


class BundleId(ApexId):
    kind = "bundle_id"


class ReleaseId(ApexId):
    kind = "release_id"
