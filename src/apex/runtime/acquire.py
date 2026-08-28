from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TypeVar

from apex.domain.models import (
    EvidenceEffect,
    EvidenceRecord,
    ProviderHealth,
    ProviderStatus,
    Qualification,
    dataclass_to_dict,
)
from apex.forecast.adapters.airsenal import load_airsenal
from apex.forecast.adapters.dastan import load_dastan
from apex.forecast.adapters.openfpl import load_openfpl
from apex.forecast.qualification import qualify_surface
from apex.governance.evidence import validate_evidence
from apex.sources.official import fetch_official_snapshot
from apex.sources.team import acquire_team_state

from .config import ApexConfig, config_sha
from .snapshot import SnapshotBuilder

T = TypeVar("T")


class AcquisitionStageError(RuntimeError):
    """A fatal acquisition error with a stable machine-readable stage."""

    def __init__(self, stage: str, cause: Exception):
        self.stage = str(stage)
        self.cause_type = type(cause).__name__
        self.cause_message = str(cause)
        super().__init__(f"{self.stage}: {self.cause_type}: {self.cause_message}")

    def as_dict(self) -> dict[str, str]:
        return {
            "stage": self.stage,
            "cause_type": self.cause_type,
            "cause_message": self.cause_message,
        }


def _stage(stage: str, fn: Callable[[], T]) -> T:
    try:
        return fn()
    except AcquisitionStageError:
        raise
    except Exception as exc:
        raise AcquisitionStageError(stage, exc) from exc


def _parse_evidence(path: Path) -> tuple[EvidenceRecord, ...]:
    if not path.exists():
        return ()
    raw = json.loads(path.read_text())
    rows = raw if isinstance(raw, list) else raw.get("records", [])
    return tuple(
        EvidenceRecord(
            str(row["evidence_id"]),
            int(row["element_id"]),
            str(row["source_name"]),
            str(row["source_url"]),
            str(row["source_tier"]),
            str(row["published_at"]),
            str(row["retrieved_at"]),
            str(row["expires_at"]),
            str(row["evidence_type"]),
            int(row["gameweek"]),
            EvidenceEffect(row["effect"]),
            str(row["content_hash"]),
            str(row.get("excerpt", "")),
        )
        for row in rows
    )


def _target_gameweek(official, now):
    future = []
    for gameweek, value in official.deadlines.items():
        deadline = datetime.fromisoformat(value.replace("Z", "+00:00"))
        deadline = deadline if deadline.tzinfo else deadline.replace(tzinfo=timezone.utc)
        if deadline > now:
            future.append(gameweek)
    if not future:
        raise RuntimeError("no future Official FPL deadline")
    return min(future)


def assert_official_acquisition_stable(
    expected_hash: str | None,
    actual_hash: str,
) -> None:
    """Fail if Official authority state changed while providers were generated."""
    if expected_hash and str(expected_hash) != str(actual_hash):
        raise RuntimeError(
            "Official FPL authority state changed during provider acquisition: "
            f"expected {expected_hash}, got {actual_hash}. "
            "Discard this attempt and restart provider acquisition from a fresh "
            "Official FPL seal."
        )


def acquire_and_freeze(
    config_path: Path,
    *,
    run_id: str,
    code_sha: str,
    run_started_at: str,
    workdir: Path = Path("."),
    expected_official_hash: str | None = None,
):
    config = _stage("config", lambda: ApexConfig.load(config_path))
    now = datetime.now(timezone.utc)

    def _reanchor():
        official, raw_official = fetch_official_snapshot(season=config.season)
        assert_official_acquisition_stable(
            expected_official_hash,
            official.source_hash,
        )
        return official, raw_official

    official, raw_official = _stage("official_reanchor", _reanchor)
    target = _stage("target_gameweek", lambda: _target_gameweek(official, now))
    team_acquisition = _stage(
        "team_state",
        lambda: acquire_team_state(config.entry_id, official, now=now),
    )
    team = team_acquisition.state
    statuses = []

    def _parse_start():
        value = datetime.fromisoformat(run_started_at.replace("Z", "+00:00"))
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    start = _stage("run_provenance", _parse_start)

    for provider_config in config.providers:
        path = workdir / provider_config.path
        surface = None
        reasons = []
        health = ProviderHealth.ERROR
        qualification_by_horizon = {
            horizon: Qualification.UNQUALIFIED
            for horizon in provider_config.requested_horizons
        }
        if path.exists():
            try:
                if provider_config.provider_id == "airsenal":
                    surface = load_airsenal(
                        path,
                        official=official,
                        target_gameweek=target,
                        trusted_source_snapshot=official.source_hash,
                    )
                elif provider_config.provider_id == "dastan":
                    surface = load_dastan(
                        path,
                        official=official,
                        target_gameweek=target,
                    )
                elif provider_config.provider_id == "openfpl":
                    surface = load_openfpl(
                        path,
                        official=official,
                        target_gameweek=target,
                    )
                else:
                    raise ValueError(
                        f"unknown provider adapter {provider_config.provider_id}"
                    )

                generated = datetime.fromisoformat(
                    surface.generated_at.replace("Z", "+00:00")
                )
                generated = (
                    generated
                    if generated.tzinfo
                    else generated.replace(tzinfo=timezone.utc)
                )
                if generated < start:
                    reasons.append("provider forecast predates this production attempt")

                qualification = qualify_surface(
                    surface,
                    official,
                    decision_universe=official.decision_universe(
                        team.squad_ids if team else frozenset()
                    ),
                    requested_horizons=provider_config.requested_horizons,
                    max_age_hours=provider_config.max_age_hours,
                    required_scoring_rules_version=config.scoring_rules_version,
                    now=now,
                )
                reasons.extend(qualification.reasons)
                health = qualification.health
                for horizon in qualification.qualified_horizons:
                    qualification_by_horizon[horizon] = Qualification.QUALIFIED
                if reasons and health == ProviderHealth.HEALTHY:
                    health = ProviderHealth.INCOMPLETE
            except Exception as exc:
                reasons.append(f"{type(exc).__name__}: {exc}")
                health = ProviderHealth.ERROR
        else:
            reasons.append(f"provider export missing: {provider_config.path}")

        statuses.append(
            ProviderStatus(
                provider_config.provider_id,
                provider_config.role,
                provider_config.priority,
                health,
                qualification_by_horizon,
                surface,
                tuple(dict.fromkeys(reasons)),
                provider_config.serve_authorized,
                provider_config.predictive_status,
            )
        )

    def _evidence_stage():
        evidence = _parse_evidence(workdir / "acquisition/evidence/hard.json")
        errors = validate_evidence(evidence, official, now=now)
        return evidence, errors

    evidence, evidence_errors = _stage("evidence", _evidence_stage)

    def _freeze():
        builder = SnapshotBuilder()
        builder.add_json("official.json", dataclass_to_dict(official))
        builder.add_json("official_raw.json", raw_official)
        builder.add_json(
            "team_state.json",
            dataclass_to_dict(team) if team else None,
        )
        builder.add_json(
            "team_state_acquisition.json",
            team_acquisition.provenance(),
        )
        builder.add_json(
            "team_transfers_public.json",
            list(team_acquisition.public_transfers),
        )
        builder.add_json(
            "evidence.json",
            [dataclass_to_dict(record) for record in evidence],
        )
        builder.add_json(
            "evidence_validation.json",
            {"errors": list(evidence_errors)},
        )

        qualification_matrix = []
        for status in statuses:
            qualification_matrix.append(
                {
                    "provider_id": status.provider_id,
                    "role": status.role.value,
                    "priority": status.priority,
                    "health": status.health.value,
                    "qualification_by_horizon": {
                        str(key): value.value
                        for key, value in status.qualification_by_horizon.items()
                    },
                    "reasons": list(status.reasons),
                    "serve_authorized": status.serve_authorized,
                    "predictive_status": status.predictive_status.value,
                    "scoring_rules_version": (
                        status.surface.scoring_rules_version
                        if status.surface
                        else None
                    ),
                }
            )
            if status.surface:
                builder.add_json(
                    f"providers/{status.provider_id}.json",
                    dataclass_to_dict(status.surface),
                )
            provider_config = next(
                provider
                for provider in config.providers
                if provider.provider_id == status.provider_id
            )
            path = workdir / provider_config.path
            if path.exists():
                builder.add_bytes(
                    f"provider_raw/{status.provider_id}{path.suffix or '.bin'}",
                    path.read_bytes(),
                )

        builder.add_json("qualification_matrix.json", qualification_matrix)
        builder.add_json(
            "run.json",
            {
                "schema_version": 1,
                "run_id": run_id,
                "code_sha": code_sha,
                "config_sha": config_sha(config_path),
                "run_started_at": run_started_at,
                "acquired_at": now.isoformat(),
                "official_pre_provider_hash": expected_official_hash,
                "official_final_hash": official.source_hash,
                "official_acquisition_stable": (
                    expected_official_hash is None
                    or expected_official_hash == official.source_hash
                ),
                "target_gameweek": target,
                "season": config.season,
                "entry_id": config.entry_id,
                "max_horizon": config.max_horizon,
                "scoring_rules_version": config.scoring_rules_version,
                "deadline": official.deadlines[target],
                "team_state_mode": team_acquisition.mode,
                "team_state_complete_for_transfers": (
                    team.state_complete_for_transfers if team else False
                ),
            },
        )
        builder.add_bytes("config.yaml", Path(config_path).read_bytes())
        return builder.freeze(
            workdir / Path(config.snapshot_dir),
            metadata={
                "run_id": run_id,
                "target_gameweek": target,
                "code_sha": code_sha,
                "official_pre_provider_hash": expected_official_hash,
                "official_final_hash": official.source_hash,
                "scoring_rules_version": config.scoring_rules_version,
                "team_state_mode": team_acquisition.mode,
            },
        )

    return _stage("freeze", _freeze)
