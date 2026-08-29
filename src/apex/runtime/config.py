from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

from apex.domain.models import ProviderRole, Qualification

CURRENT_SCORING_RULES_VERSION = "fpl-2026-27-v1"


@dataclass(frozen=True)
class ProviderConfig:
    provider_id: str
    role: ProviderRole
    priority: int
    serve_authorized: bool
    max_age_hours: float
    requested_horizons: tuple[int, ...]
    predictive_status: Qualification
    path: str


@dataclass(frozen=True)
class EvidenceConfig:
    required: bool = False
    records_path: str = "acquisition/evidence/hard.json"
    manifest_path: str = "acquisition/evidence/acquisition.json"


@dataclass(frozen=True)
class ApexConfig:
    season: str
    entry_id: int
    max_horizon: int
    providers: tuple[ProviderConfig, ...]
    scoring_rules_version: str = CURRENT_SCORING_RULES_VERSION
    snapshot_dir: str = "data/v2/snapshots"
    release_prefix: str = "apex-v2"
    evidence: EvidenceConfig = EvidenceConfig()

    @classmethod
    def load(cls, path):
        payload = yaml.safe_load(Path(path).read_text())
        providers = []
        for item in payload["providers"]:
            providers.append(
                ProviderConfig(
                    item["id"],
                    ProviderRole(item["role"]),
                    int(item.get("priority", 100)),
                    bool(item.get("serve_authorized", False)),
                    float(item.get("max_age_hours", 18)),
                    tuple(map(int, item.get("requested_horizons", [1]))),
                    Qualification(
                        item.get("predictive_status", "INSUFFICIENT_HISTORY")
                    ),
                    str(item["path"]),
                )
            )
        evidence = payload.get("evidence") or {}
        return cls(
            season=str(payload.get("season", "2026-2027")),
            entry_id=int(payload["entry_id"]),
            max_horizon=int(payload.get("max_horizon", 8)),
            providers=tuple(providers),
            scoring_rules_version=str(
                payload.get("scoring_rules_version", CURRENT_SCORING_RULES_VERSION)
            ),
            snapshot_dir=str(payload.get("snapshot_dir", "data/v2/snapshots")),
            release_prefix=str(payload.get("release_prefix", "apex-v2")),
            evidence=EvidenceConfig(
                required=bool(evidence.get("required", False)),
                records_path=str(
                    evidence.get("records_path", "acquisition/evidence/hard.json")
                ),
                manifest_path=str(
                    evidence.get(
                        "manifest_path", "acquisition/evidence/acquisition.json"
                    )
                ),
            ),
        )


def config_sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
