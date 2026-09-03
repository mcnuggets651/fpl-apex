from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
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
from apex.forecast.adapters.apex_proprietary import load_apex_proprietary
from apex.forecast.adapters.dastan import load_dastan
from apex.forecast.adapters.openfpl import load_openfpl
from apex.forecast.adapters.pitchside import load_pitchside
from apex.forecast.qualification import qualify_surface
from apex.governance.evidence import validate_evidence
from apex.sources.evidence import collect_v2_evidence
from apex.sources.official import fetch_official_snapshot
from apex.sources.pitchside import acquire_pitchside_shadow
from apex.sources.team import acquire_team_state

from .config import ApexConfig, production_core_sha
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


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_records_hash(records: tuple[EvidenceRecord, ...]) -> str:
    payload = [dataclass_to_dict(record) for record in records]
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return _sha256(encoded)


def _parse_evidence_payload(raw) -> tuple[EvidenceRecord, ...]:
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


def _parse_evidence(path: Path) -> tuple[EvidenceRecord, ...]:
    if not path.exists():
        return ()
    return _parse_evidence_payload(json.loads(path.read_text(encoding="utf-8")))


def _validate_evidence_manifest(
    payload: dict,
    records: tuple[EvidenceRecord, ...],
    *,
    required: bool,
    official_hash: str,
    target_gameweek: int,
) -> dict:
    if not isinstance(payload, dict) or int(payload.get("schema_version", 0)) != 1:
        raise RuntimeError("external evidence acquisition manifest schema invalid")
    if required and payload.get("completed") is not True:
        raise RuntimeError("required external evidence acquisition did not complete")
    if str(payload.get("observed_official_hash") or "") != str(official_hash):
        raise RuntimeError(
            "external evidence Official FPL hash does not match final authority anchor"
        )
    if int(payload.get("target_gameweek", -1)) != int(target_gameweek):
        raise RuntimeError(
            "external evidence target gameweek does not match final authority anchor"
        )
    if int(payload.get("record_count", -1)) != len(records):
        raise RuntimeError(
            "external evidence manifest record count does not match evidence payload"
        )
    expected_records_hash = str(payload.get("records_sha256") or "").lower()
    if required and not expected_records_hash:
        raise RuntimeError(
            "required external evidence acquisition manifest does not bind evidence payload hash"
        )
    if expected_records_hash and expected_records_hash != _canonical_records_hash(records):
        raise RuntimeError("external evidence payload hash does not match acquisition manifest")
    failures = payload.get("required_source_failures") or []
    if required and failures:
        raise RuntimeError(
            "required external evidence source failures remain: "
            + ", ".join(map(str, failures))
        )
    return payload


def _validate_evidence_acquisition(
    manifest_path: Path,
    records: tuple[EvidenceRecord, ...],
    *,
    required: bool,
    official_hash: str,
    target_gameweek: int,
) -> dict:
    if not manifest_path.exists():
        if required:
            raise RuntimeError("required external evidence acquisition manifest is missing")
        return {
            "schema_version": 1,
            "completed": False,
            "required": False,
            "mode": "NOT_REQUIRED",
            "observed_official_hash": str(official_hash),
            "target_gameweek": int(target_gameweek),
            "record_count": len(records),
            "records_sha256": _canonical_records_hash(records),
            "required_source_failures": [],
        }
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return _validate_evidence_manifest(
        payload,
        records,
        required=required,
        official_hash=official_hash,
        target_gameweek=target_gameweek,
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


def assert_private_manager_credential_opt_in() -> None:
    """Fail closed if owner credentials are present without an explicit opt-in."""
    flag = os.getenv("APEX_ENABLE_PRIVATE_MANAGER_STATE", "0").strip()
    if flag not in {"0", "1"}:
        raise RuntimeError("APEX_ENABLE_PRIVATE_MANAGER_STATE must be exactly '0' or '1'")
    credentials_present = bool(
        os.getenv("FPL_SESSION_COOKIE", "").strip()
        or os.getenv("FPL_X_API_AUTHORIZATION", "").strip()
    )
    if credentials_present and flag != "1":
        raise RuntimeError(
            "owner FPL credentials are present but private manager-state "
            "acquisition is not explicitly enabled"
        )
    if flag == "1" and not credentials_present:
        raise RuntimeError(
            "private manager-state acquisition is enabled but no FPL owner "
            "credential is present"
        )


def _assert_file_unchanged(path: Path, expected: bytes, label: str) -> None:
    try:
        observed = path.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"{label} disappeared during acquisition") from exc
    if observed != expected:
        raise RuntimeError(f"{label} changed during acquisition")


def _load_captured_config(config_bytes: bytes) -> ApexConfig:
    with tempfile.TemporaryDirectory(prefix="apex-v2-config-") as directory:
        captured = Path(directory) / "apex_v2.yaml"
        captured.write_bytes(config_bytes)
        return ApexConfig.load(captured)


def acquire_and_freeze(
    config_path: Path,
    *,
    run_id: str,
    code_sha: str,
    run_started_at: str,
    workdir: Path = Path("."),
    expected_official_hash: str | None = None,
):
    config_path = Path(config_path)
    workdir = Path(workdir)
    config_bytes = _stage("config_integrity", config_path.read_bytes)
    config = _stage("config", lambda: _load_captured_config(config_bytes))
    _stage(
        "config_integrity",
        lambda: _assert_file_unchanged(config_path, config_bytes, "Apex config"),
    )
    config_digest = _sha256(config_bytes)
    now = datetime.now(timezone.utc)

    evidence_seed: tuple[tuple[EvidenceRecord, ...], dict] | None = None
    evidence_sources_bytes: bytes | None = None
    evidence_sources_path = workdir / config.evidence.sources_path

    if config.evidence.required:
        evidence_sources_bytes = _stage(
            "evidence_integrity",
            evidence_sources_path.read_bytes,
        )
        with tempfile.TemporaryDirectory(prefix="apex-v2-evidence-sources-") as directory:
            staged_sources = Path(directory) / evidence_sources_path.name
            staged_sources.write_bytes(evidence_sources_bytes)
            collection = _stage(
                "external_evidence",
                lambda: collect_v2_evidence(
                    sources_path=staged_sources,
                    records_path=workdir / config.evidence.records_path,
                    manifest_path=workdir / config.evidence.manifest_path,
                    expected_official_hash=expected_official_hash,
                    season=config.season,
                    now=now,
                ),
            )
        _stage(
            "evidence_integrity",
            lambda: _assert_file_unchanged(
                evidence_sources_path,
                evidence_sources_bytes,
                "evidence source configuration",
            ),
        )
        records_path = workdir / config.evidence.records_path
        manifest_path = workdir / config.evidence.manifest_path
        records = tuple(getattr(collection, "records", _parse_evidence(records_path)))
        disk_records = _stage("evidence_integrity", lambda: _parse_evidence(records_path))
        if disk_records != records:
            raise AcquisitionStageError(
                "evidence_integrity",
                RuntimeError("evidence record payload changed during acquisition"),
            )
        manifest = dict(
            getattr(
                collection,
                "manifest",
                json.loads(manifest_path.read_text(encoding="utf-8")),
            )
        )
        manifest["records_sha256"] = _canonical_records_hash(records)
        source_hash = _sha256(evidence_sources_bytes)
        observed_source_hash = str(manifest.get("source_config_sha256") or "").lower()
        if observed_source_hash and observed_source_hash != source_hash:
            raise AcquisitionStageError(
                "evidence_integrity",
                RuntimeError(
                    "evidence source configuration hash does not match collector provenance"
                ),
            )
        manifest["source_config_sha256"] = source_hash
        evidence_seed = (records, manifest)

    optional_provider_errors: dict[str, str] = {}
    for provider_config in config.providers:
        if provider_config.provider_id not in {"pitchside", "apex_proprietary"}:
            continue
        path = workdir / provider_config.path
        if path.exists():
            continue
        try:
            if provider_config.provider_id == "pitchside":
                acquire_pitchside_shadow(
                    path,
                    season=config.season,
                    expected_official_hash=expected_official_hash,
                    now=now,
                )
            else:
                if not expected_official_hash:
                    raise RuntimeError(
                        "Apex proprietary shadow requires the pre-provider Official seal"
                    )
                script = workdir / "scripts/acquire_apex_proprietary_shadow.py"
                subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "--expected-official-hash",
                        str(expected_official_hash),
                        "--code-sha",
                        str(code_sha),
                        "--season",
                        str(config.season),
                        "--horizon",
                        str(config.max_horizon),
                        "--output",
                        str(path),
                    ],
                    cwd=workdir,
                    check=True,
                    timeout=1200,
                )
        except Exception as exc:
            optional_provider_errors[provider_config.provider_id] = (
                f"{type(exc).__name__}: {exc}"
            )

    def _reanchor():
        official, raw_official = fetch_official_snapshot(season=config.season)
        assert_official_acquisition_stable(expected_official_hash, official.source_hash)
        return official, raw_official

    official, raw_official = _stage("official_reanchor", _reanchor)
    target = _stage("target_gameweek", lambda: _target_gameweek(official, now))
    _stage("private_manager_opt_in", assert_private_manager_credential_opt_in)
    team_acquisition = _stage(
        "team_state",
        lambda: acquire_team_state(config.entry_id, official, now=now),
    )
    team = team_acquisition.state
    statuses = []
    provider_raw: dict[str, tuple[bytes, str]] = {}

    def _parse_start():
        value = datetime.fromisoformat(run_started_at.replace("Z", "+00:00"))
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    start = _stage("run_provenance", _parse_start)

    for provider_config in config.providers:
        path = workdir / provider_config.path
        surface = None
        reasons = []
        if provider_config.provider_id in optional_provider_errors:
            reasons.append(
                "optional provider acquisition failed: "
                + optional_provider_errors[provider_config.provider_id]
            )
        health = ProviderHealth.ERROR
        qualification_by_horizon = {
            horizon: Qualification.UNQUALIFIED
            for horizon in provider_config.requested_horizons
        }
        if path.exists():
            raw_bytes = _stage("provider_integrity", path.read_bytes)
            try:
                with tempfile.TemporaryDirectory(
                    prefix=f"apex-v2-provider-{provider_config.provider_id}-"
                ) as directory:
                    staged_path = Path(directory) / path.name
                    staged_path.write_bytes(raw_bytes)
                    if provider_config.provider_id == "airsenal":
                        surface = load_airsenal(
                            staged_path,
                            official=official,
                            target_gameweek=target,
                            trusted_source_snapshot=official.source_hash,
                        )
                    elif provider_config.provider_id == "dastan":
                        surface = load_dastan(
                            staged_path,
                            official=official,
                            target_gameweek=target,
                        )
                    elif provider_config.provider_id == "pitchside":
                        surface = load_pitchside(
                            staged_path,
                            official=official,
                            target_gameweek=target,
                            scoring_rules_version=config.scoring_rules_version,
                            max_horizon=max(provider_config.requested_horizons),
                        )
                    elif provider_config.provider_id == "apex_proprietary":
                        surface = load_apex_proprietary(
                            staged_path,
                            official=official,
                            target_gameweek=target,
                        )
                    elif provider_config.provider_id == "openfpl":
                        surface = load_openfpl(
                            staged_path,
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

            _stage(
                "provider_integrity",
                lambda path=path, raw_bytes=raw_bytes, provider_id=provider_config.provider_id: (
                    _assert_file_unchanged(
                        path,
                        raw_bytes,
                        f"provider export {provider_id}",
                    )
                ),
            )
            provider_raw[provider_config.provider_id] = (
                raw_bytes,
                path.suffix or ".bin",
            )
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
        nonlocal evidence_sources_bytes
        if evidence_seed is not None:
            evidence, acquisition = evidence_seed
        else:
            records_path = workdir / config.evidence.records_path
            manifest_path = workdir / config.evidence.manifest_path
            if config.evidence.required and not records_path.exists():
                raise RuntimeError("required external evidence record payload is missing")
            evidence = _parse_evidence(records_path)
            acquisition = _validate_evidence_acquisition(
                manifest_path,
                evidence,
                required=config.evidence.required,
                official_hash=official.source_hash,
                target_gameweek=target,
            )
            if evidence_sources_path.exists():
                evidence_sources_bytes = evidence_sources_path.read_bytes()

        acquisition = _validate_evidence_manifest(
            acquisition,
            evidence,
            required=config.evidence.required,
            official_hash=official.source_hash,
            target_gameweek=target,
        )
        if evidence_sources_bytes is not None:
            expected_source_hash = str(
                acquisition.get("source_config_sha256") or ""
            ).lower()
            if config.evidence.required and not expected_source_hash:
                raise RuntimeError(
                    "required evidence manifest does not bind source configuration"
                )
            if expected_source_hash and expected_source_hash != _sha256(
                evidence_sources_bytes
            ):
                raise RuntimeError(
                    "evidence source configuration hash does not match acquisition manifest"
                )
        errors = validate_evidence(evidence, official, now=now)
        return evidence, errors, acquisition

    evidence, evidence_errors, evidence_acquisition = _stage("evidence", _evidence_stage)

    _stage(
        "config_integrity",
        lambda: _assert_file_unchanged(config_path, config_bytes, "Apex config"),
    )
    if config.evidence.required and evidence_sources_bytes is not None:
        _stage(
            "evidence_integrity",
            lambda: _assert_file_unchanged(
                evidence_sources_path,
                evidence_sources_bytes,
                "evidence source configuration",
            ),
        )

    def _freeze():
        builder = SnapshotBuilder()
        builder.add_json("official.json", dataclass_to_dict(official))
        builder.add_json("official_raw.json", raw_official)
        builder.add_json("team_state.json", dataclass_to_dict(team) if team else None)
        builder.add_json("team_state_acquisition.json", team_acquisition.provenance())
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
        builder.add_json("evidence_acquisition.json", evidence_acquisition)
        builder.add_json(
            "evidence_records_raw.json",
            {
                "schema_version": 1,
                "records": [dataclass_to_dict(record) for record in evidence],
            },
        )
        if evidence_sources_bytes is not None:
            builder.add_bytes("evidence_sources.yaml", evidence_sources_bytes)

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
                        status.surface.scoring_rules_version if status.surface else None
                    ),
                }
            )
            if status.surface:
                builder.add_json(
                    f"providers/{status.provider_id}.json",
                    dataclass_to_dict(status.surface),
                )
            captured = provider_raw.get(status.provider_id)
            if captured is not None:
                raw_bytes, suffix = captured
                builder.add_bytes(
                    f"provider_raw/{status.provider_id}{suffix}",
                    raw_bytes,
                )

        builder.add_json("qualification_matrix.json", qualification_matrix)
        frozen_at = datetime.now(timezone.utc).isoformat()
        evidence_complete = bool(evidence_acquisition.get("completed", False))
        evidence_records_hash = _canonical_records_hash(evidence)
        evidence_source_hash = (
            _sha256(evidence_sources_bytes)
            if evidence_sources_bytes is not None
            else None
        )
        builder.add_json(
            "run.json",
            {
                "schema_version": 1,
                "run_id": run_id,
                "code_sha": code_sha,
                "config_sha": config_digest,
                "production_core_sha": production_core_sha(config),
                "run_started_at": run_started_at,
                "acquired_at": now.isoformat(),
                "frozen_at": frozen_at,
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
                "evidence_required": config.evidence.required,
                "evidence_acquisition_complete": evidence_complete,
                "evidence_record_count": len(evidence),
                "evidence_records_sha256": evidence_records_hash,
                "evidence_source_config_sha256": evidence_source_hash,
            },
        )
        builder.add_bytes("config.yaml", config_bytes)
        return builder.freeze(
            workdir / Path(config.snapshot_dir),
            metadata={
                "run_id": run_id,
                "target_gameweek": target,
                "code_sha": code_sha,
                "config_sha": config_digest,
                "frozen_at": frozen_at,
                "official_pre_provider_hash": expected_official_hash,
                "official_final_hash": official.source_hash,
                "scoring_rules_version": config.scoring_rules_version,
                "team_state_mode": team_acquisition.mode,
                "evidence_required": config.evidence.required,
                "evidence_acquisition_complete": evidence_complete,
                "evidence_records_sha256": evidence_records_hash,
                "evidence_source_config_sha256": evidence_source_hash,
            },
        )

    return _stage("freeze", _freeze)
