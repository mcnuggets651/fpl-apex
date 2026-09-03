from __future__ import annotations

import hashlib
import json
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
    sources_path: str = "config/news_sources.yaml"
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
                sources_path=str(
                    evidence.get("sources_path", "config/news_sources.yaml")
                ),
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


def production_core_sha(config: ApexConfig) -> str:
    """Identity of the currently-authorized production core, distinct from
    `config_sha`.

    `config_sha` hashes the entire raw config file, so it changes on any
    edit whatsoever -- including ones with zero bearing on which provider
    is authorized to serve (e.g. `snapshot_dir`, `release_prefix`). That
    makes it useless for answering "did production authority actually
    change", which is exactly the question a consumer verifying a private
    manager attempt against current authority needs answered.

    `production_core_sha` hashes only the governance-relevant slice: for
    each provider, its id, role, serve_authorized flag and priority (the
    fields that jointly determine which provider(s) may serve and in what
    order), plus the scoring rules version. Providers are sorted by id so
    the hash is independent of their order in the config file. Unrelated
    config edits (paths, snapshot directories, evidence config) do not
    change this value; a genuine promotion (role/serve_authorized/priority
    change for any provider) always does.
    """
    governed = {
        "scoring_rules_version": config.scoring_rules_version,
        "providers": sorted(
            (
                {
                    "provider_id": provider.provider_id,
                    "role": provider.role.value,
                    "serve_authorized": provider.serve_authorized,
                    "priority": provider.priority,
                }
                for provider in config.providers
            ),
            key=lambda row: row["provider_id"],
        ),
    }
    canonical = json.dumps(governed, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
