from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from apex.domain.models import ProviderRole, Qualification

CURRENT_SCORING_RULES_VERSION = "fpl-2026-27-v1"


def _strict_bool(value: Any, *, field: str, default: bool | None = None) -> bool:
    if value is None and default is not None:
        return default
    if type(value) is not bool:
        raise ValueError(f"{field} must be an explicit boolean")
    return value


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
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Apex config root must be a mapping")
        if int(payload.get("schema_version", 1)) != 1:
            raise ValueError("unsupported Apex config schema_version")

        max_horizon = int(payload.get("max_horizon", 8))
        if max_horizon <= 0:
            raise ValueError("max_horizon must be positive")

        raw_providers = payload.get("providers")
        if not isinstance(raw_providers, list):
            raise ValueError("providers must be a list")

        providers = []
        provider_ids: set[str] = set()
        for index, item in enumerate(raw_providers):
            if not isinstance(item, dict):
                raise ValueError(f"provider entry {index} must be a mapping")
            provider_id = str(item.get("id") or "").strip()
            if not provider_id:
                raise ValueError(f"provider entry {index} has empty id")
            if provider_id in provider_ids:
                raise ValueError(f"duplicate provider id: {provider_id}")
            provider_ids.add(provider_id)

            max_age_hours = float(item.get("max_age_hours", 18))
            if not math.isfinite(max_age_hours) or max_age_hours <= 0:
                raise ValueError(
                    f"provider {provider_id} max_age_hours must be positive"
                )

            raw_horizons = item.get("requested_horizons", [1])
            if not isinstance(raw_horizons, (list, tuple)) or not raw_horizons:
                raise ValueError(
                    f"provider {provider_id} requested_horizons must be non-empty"
                )
            requested_horizons = tuple(map(int, raw_horizons))
            if (
                len(set(requested_horizons)) != len(requested_horizons)
                or any(horizon < 1 or horizon > max_horizon for horizon in requested_horizons)
            ):
                raise ValueError(
                    f"provider {provider_id} requested_horizons must be unique and "
                    f"within 1..{max_horizon}"
                )

            provider_path = str(item.get("path") or "").strip()
            if not provider_path:
                raise ValueError(f"provider {provider_id} path must be non-empty")

            providers.append(
                ProviderConfig(
                    provider_id,
                    ProviderRole(item["role"]),
                    int(item.get("priority", 100)),
                    _strict_bool(
                        item.get("serve_authorized"),
                        field=f"provider {provider_id} serve_authorized",
                        default=False,
                    ),
                    max_age_hours,
                    requested_horizons,
                    Qualification(
                        item.get("predictive_status", "INSUFFICIENT_HISTORY")
                    ),
                    provider_path,
                )
            )

        evidence = payload.get("evidence") or {}
        if not isinstance(evidence, dict):
            raise ValueError("evidence config must be a mapping")

        return cls(
            season=str(payload.get("season", "2026-2027")),
            entry_id=int(payload["entry_id"]),
            max_horizon=max_horizon,
            providers=tuple(providers),
            scoring_rules_version=str(
                payload.get("scoring_rules_version", CURRENT_SCORING_RULES_VERSION)
            ),
            snapshot_dir=str(payload.get("snapshot_dir", "data/v2/snapshots")),
            release_prefix=str(payload.get("release_prefix", "apex-v2")),
            evidence=EvidenceConfig(
                required=_strict_bool(
                    evidence.get("required"),
                    field="evidence required",
                    default=False,
                ),
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
