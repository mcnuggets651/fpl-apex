from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import tarfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from apex.runtime.snapshot import open_frozen_snapshot

PUBLIC_RELEASE_ASSETS_V1 = frozenset(
    {
        "public_attempt.json",
        "canonical_forecast.json",
        "provider_forecasts.tar.gz",
        "governance.json",
        "evidence.json",
        "attestation.json",
    }
)
INTENT_RELEASE_ASSETS_V1 = frozenset({"intent.json"})
DIAGNOSTIC_ARTIFACT_ASSETS_V1 = frozenset(
    {
        "public_attempt.json",
        "governance.json",
        "attestation.json",
        "publication_summary.json",
    }
)
PRIVATE_RELEASE_ASSETS_V1 = frozenset(
    {"private_manager_attempt.json", "private_attestation.json"}
)

INTENT_FIELDS_V1 = frozenset(
    {"schema_version", "run_id", "season", "gameweek", "code_sha", "started_at"}
)

PUBLIC_EVIDENCE_FIELDS_V1 = (
    "evidence_id",
    "element_id",
    "source_name",
    "source_url",
    "source_tier",
    "published_at",
    "retrieved_at",
    "expires_at",
    "evidence_type",
    "gameweek",
    "effect",
    "content_hash",
    "excerpt",
)

OFFICIAL_PLAYER_FIELDS_V1 = (
    "element_id",
    "web_name",
    "team_id",
    "position",
    "price_tenths",
    "status",
    "can_transact",
    "fpl_code",
)
OFFICIAL_FIXTURE_FIELDS_V1 = (
    "fixture_id",
    "gameweek",
    "home_team_id",
    "away_team_id",
    "kickoff_time",
)
OFFICIAL_TEAM_FIELDS_V1 = (
    "id",
    "name",
    "short_name",
)

PROJECTION_SURFACE_FIELDS_V1 = (
    "schema_version",
    "provider_id",
    "provider_version",
    "generated_at",
    "season",
    "source_snapshot",
    "scoring_rules_version",
    "supported_horizons",
    "runtime_dependencies",
    "rows",
)
PROJECTION_ROW_FIELDS_V1 = (
    "element_id",
    "gameweek",
    "horizon",
    "expected_points",
    "fixture_ids",
    "n_fixtures",
    "player_status_at_forecast",
    "expected_minutes",
    "p_appearance",
    "p_start",
    "p_60",
    "coverage_status",
    "coverage_reason",
    "metadata",
)

HMAC_DOMAIN_V1 = b"apex-v2-private-decision-v1\x00"
PUBLIC_MODE = "PUBLIC_DEADLINE_FALLBACK"
NO_PUBLIC_DEADLINE_MODE = "NO_PUBLIC_DEADLINE"
AUTHENTICATED_MODE = "AUTHENTICATED_MY_TEAM"


class ExposureClass(StrEnum):
    PUBLIC_CANONICAL = "PUBLIC_CANONICAL"
    PUBLIC_RESEARCH = "PUBLIC_RESEARCH"
    GOVERNANCE_PUBLIC = "GOVERNANCE_PUBLIC"
    PRIVATE_MANAGER = "PRIVATE_MANAGER"
    OPERATIONAL_SENSITIVE = "OPERATIONAL_SENSITIVE"
    PRIVATE_DRAFT = "PRIVATE_DRAFT"
    SECRET = "SECRET"
    UNCLASSIFIED = "UNCLASSIFIED"


@dataclass(frozen=True)
class PublicationMaterial:
    public_files: dict[str, Path]
    private_files: dict[str, Path]
    diagnostics_files: dict[str, Path]
    public_attempt_id: str
    private_attempt_id: str | None
    authenticated_manager_state: bool


def canonical_json_bytes(payload) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(payload) + b"\n")
    return path


def assert_exact_asset_set(
    files: dict[str, Path],
    allowed: frozenset[str],
    label: str,
) -> None:
    names = frozenset(files)
    if names != allowed:
        raise RuntimeError(
            f"{label} asset set mismatch: {sorted(names)} != {sorted(allowed)}"
        )
    for name, path in files.items():
        if not Path(path).is_file():
            raise RuntimeError(f"{label} asset missing on disk: {name}")


def validate_intent_payload(payload: dict) -> None:
    fields = frozenset(payload)
    if fields != INTENT_FIELDS_V1:
        raise RuntimeError(
            f"intent schema field mismatch: {sorted(fields)} != {sorted(INTENT_FIELDS_V1)}"
        )
    if payload.get("schema_version") != 1:
        raise RuntimeError("unsupported intent schema version")


def _project_fields(payload: dict, fields: tuple[str, ...]) -> dict:
    return {field: payload.get(field) for field in fields}


def _sanitize_provider_surface(raw: dict) -> dict:
    out = _project_fields(raw, PROJECTION_SURFACE_FIELDS_V1)
    rows = []
    for raw_row in raw.get("rows", []):
        row = _project_fields(raw_row, PROJECTION_ROW_FIELDS_V1)
        row["metadata"] = {}
        rows.append(row)
    out["rows"] = rows
    return out


def _sanitize_public_evidence(rows: list[dict]) -> list[dict]:
    return [_project_fields(row, PUBLIC_EVIDENCE_FIELDS_V1) for row in rows]


def _official_catalog(snapshot) -> dict:
    official = snapshot.read_json("official.json")
    try:
        raw = snapshot.read_json("official_raw.json")
    except FileNotFoundError:
        raw = {}
    return {
        "schema_version": 1,
        "season": official.get("season"),
        "acquired_at": official.get("acquired_at"),
        "source_hash": official.get("source_hash"),
        "players": [
            _project_fields(player, OFFICIAL_PLAYER_FIELDS_V1)
            for player in official.get("players", [])
        ],
        "fixtures": [
            _project_fields(fixture, OFFICIAL_FIXTURE_FIELDS_V1)
            for fixture in official.get("fixtures", [])
        ],
        "deadlines": official.get("deadlines") or {},
        "teams": [
            _project_fields(team, OFFICIAL_TEAM_FIELDS_V1)
            for team in raw.get("teams", [])
            if isinstance(team, dict)
        ],
    }


def _acquisition(snapshot) -> dict:
    try:
        return snapshot.read_json("team_state_acquisition.json")
    except FileNotFoundError:
        return {
            "mode": "UNCLASSIFIED",
            "credential_present": None,
            "purchase_price_count": None,
            "selling_price_count": None,
            "public_transfer_ledger": {},
        }


def _assert_public_transfer_ledger(acquisition: dict) -> None:
    ledger = acquisition.get("public_transfer_ledger") or {}
    target_rows = ledger.get("target_gameweek_row_count")
    last_visible = ledger.get("last_visible_event")
    events = ledger.get("events") or []
    target_gameweek = acquisition.get("target_gameweek")
    if target_rows not in (0, None):
        raise RuntimeError("public transfer ledger contains target-gameweek rows")
    if (
        target_gameweek is not None
        and last_visible is not None
        and int(last_visible) >= int(target_gameweek)
    ):
        raise RuntimeError("public transfer ledger extends into the target gameweek")
    if target_gameweek is not None and any(
        int(event) >= int(target_gameweek) for event in events
    ):
        raise RuntimeError(
            "public transfer ledger contains an event not yet deadline-public"
        )


def _manager_state_mode(acquisition: dict) -> tuple[str, bool]:
    mode = acquisition.get("mode")
    credential_present = acquisition.get("credential_present")
    if mode not in {PUBLIC_MODE, NO_PUBLIC_DEADLINE_MODE, AUTHENTICATED_MODE}:
        raise RuntimeError(f"unknown team-state acquisition mode: {mode!r}")
    if credential_present not in {True, False}:
        raise RuntimeError("credential_present must be an explicit boolean")
    if mode in {PUBLIC_MODE, NO_PUBLIC_DEADLINE_MODE} and credential_present is not False:
        raise RuntimeError("public manager-state mode cannot report owner credentials")
    if mode == AUTHENTICATED_MODE and credential_present is not True:
        raise RuntimeError("authenticated team state must report owner credentials")
    return mode, bool(credential_present)


def _required_sha256(decision: dict, key: str) -> str:
    value = str(decision.get(key) or "").lower()
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise RuntimeError(f"DecisionBundle {key} is not a valid SHA-256 digest")
    return value


def _manager_actionability(acquisition: dict, decision: dict) -> dict:
    mode, _ = _manager_state_mode(acquisition)
    certification = decision.get("certification") or {}
    engine_actionable = bool(certification.get("actionable"))
    system = decision.get("system_decision") or {}
    decision_mode = str(system.get("decision_mode") or "NO_DECISION")
    state_complete = bool(acquisition.get("state_complete_for_transfers", False))

    authenticated = mode == AUTHENTICATED_MODE
    current_team_known = authenticated
    lineup_actionable = bool(engine_actionable and current_team_known and system)
    transfer_actionable = bool(
        lineup_actionable
        and state_complete
        and decision_mode == "TRANSFER_HORIZON"
    )
    personalized_actionable = lineup_actionable

    if transfer_actionable:
        scope = "FULL_MANAGER"
    elif lineup_actionable:
        scope = "CURRENT_TEAM_ONLY"
    elif mode == PUBLIC_MODE and engine_actionable and system:
        scope = "PUBLIC_LAST_DEADLINE_CONDITIONAL"
    else:
        scope = "NONE"

    return {
        "schema_version": 1,
        "manager_state_scope": scope,
        "engine_actionable": engine_actionable,
        "personalized_actionable": personalized_actionable,
        "lineup_actionable": lineup_actionable,
        "transfer_actionable": transfer_actionable,
        "current_editable_team_verified": current_team_known,
        "exact_transfer_state_verified": bool(current_team_known and state_complete),
        "decision_mode": decision_mode,
    }


def _provider_forecast_archive(
    snapshot,
    output: Path,
) -> tuple[Path, dict[str, str]]:
    """Publish provider provenance without redistributing forecast rows.

    The frozen provider surfaces remain part of the sealed local snapshot and
    are identified here by SHA-256. The public canonical forecast is also
    commitment-only; raw provider and serving rows remain private.
    """
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    entries: dict[str, str] = {}
    provider_names = sorted(
        name
        for name in snapshot.manifest.get("files", {})
        if name.startswith("providers/") and name.endswith(".json")
    )
    if not provider_names:
        raise RuntimeError("public provider provenance archive would be empty")
    staging = output.parent / ".provider-publication"
    if staging.exists():
        for path in sorted(staging.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    staging.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(output, "w:gz") as archive:
            for name in provider_names:
                raw = snapshot.read_json(name)
                frozen = (snapshot.manifest.get("files") or {}).get(name) or {}
                frozen_sha = str(frozen.get("sha256") or "").lower()
                if len(frozen_sha) != 64 or any(
                    char not in "0123456789abcdef" for char in frozen_sha
                ):
                    raise RuntimeError(
                        f"frozen provider surface lacks valid SHA-256 identity: {name}"
                    )
                provenance = {
                    "schema_version": 1,
                    "publication_contract": "PROVENANCE_ONLY_V1",
                    "forecast_rows_published": False,
                    "provider_id": raw.get("provider_id"),
                    "provider_version": raw.get("provider_version"),
                    "generated_at": raw.get("generated_at"),
                    "season": raw.get("season"),
                    "source_snapshot": raw.get("source_snapshot"),
                    "scoring_rules_version": raw.get("scoring_rules_version"),
                    "supported_horizons": raw.get("supported_horizons") or [],
                    "runtime_dependencies": raw.get("runtime_dependencies") or [],
                    "frozen_provider_sha256": frozen_sha,
                    "frozen_provider_bytes": int(frozen.get("bytes") or 0),
                }
                staged = staging / name
                write_json(staged, provenance)
                archive.add(staged, arcname=name)
                entries[name] = sha256_file(staged)
    finally:
        if staging.exists():
            for path in sorted(staging.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            staging.rmdir()
    return output, entries


def _canonical_forecast(snapshot, decision: dict, run: dict) -> dict:
    """Build the full canonical serving/display surface.

    This surface is required for the authenticated owner experience and exact
    audit/replay, but is PRIVATE_MANAGER material. Public publication receives
    only `_canonical_forecast_commitment` below.
    """
    diagnostics = decision.get("provider_diagnostics") or {}
    max_horizon = int(diagnostics.get("max_contiguous_horizon") or 0)
    serving = {
        int(k): str(v)
        for k, v in (
            diagnostics.get("serving_provider_by_horizon") or {}
        ).items()
    }
    if set(serving) != set(range(1, max_horizon + 1)):
        if max_horizon != 0 or serving:
            raise RuntimeError(
                "serving provider map is not contiguous over qualified horizon"
            )
    rows = []
    provider_versions = {}
    scoring_rules = set()
    for horizon in range(1, max_horizon + 1):
        provider_id = serving[horizon]
        raw = _sanitize_provider_surface(
            snapshot.read_json(f"providers/{provider_id}.json")
        )
        provider_versions[provider_id] = raw.get("provider_version")
        if raw.get("scoring_rules_version"):
            scoring_rules.add(raw["scoring_rules_version"])
        for row in raw.get("rows", []):
            if int(row.get("horizon", -1)) != horizon:
                continue
            projected = dict(row)
            projected["serving_provider_id"] = provider_id
            rows.append(projected)
    if len(scoring_rules) > 1:
        raise RuntimeError(
            "serving providers disagree on scoring-rules version"
        )
    return {
        "schema_version": 1,
        "exposure_class": ExposureClass.PRIVATE_MANAGER.value,
        "season": run["season"],
        "target_gameweek": int(run["target_gameweek"]),
        "max_contiguous_qualified_horizon": max_horizon,
        "serving_provider_by_horizon": {
            str(k): v for k, v in sorted(serving.items())
        },
        "provider_versions": provider_versions,
        "scoring_rules_version": next(iter(scoring_rules), None),
        "canonical_projection_sha256": _required_sha256(
            decision, "canonical_projection_hash"
        ),
        "official": _official_catalog(snapshot),
        "rows": rows,
    }


def _canonical_forecast_commitment(canonical: dict) -> dict:
    official = canonical.get("official") or {}
    rows = canonical.get("rows") or []
    private_surface_sha = sha256_bytes(canonical_json_bytes(canonical))
    return {
        "schema_version": 2,
        "exposure_class": ExposureClass.GOVERNANCE_PUBLIC.value,
        "content_contract": "PROJECTION_COMMITMENT_ONLY_V2",
        "forecast_rows_published": False,
        "official_catalog_published": False,
        "season": canonical.get("season"),
        "target_gameweek": canonical.get("target_gameweek"),
        "max_contiguous_qualified_horizon": canonical.get(
            "max_contiguous_qualified_horizon", 0
        ),
        "serving_provider_by_horizon": canonical.get(
            "serving_provider_by_horizon", {}
        ),
        "provider_versions": canonical.get("provider_versions", {}),
        "scoring_rules_version": canonical.get("scoring_rules_version"),
        "canonical_projection_sha256": canonical.get(
            "canonical_projection_sha256"
        ),
        "official_snapshot_sha256": official.get("source_hash"),
        "private_canonical_forecast_sha256": private_surface_sha,
        "projection_row_count": len(rows),
        "official_player_count": len(official.get("players") or []),
        "official_fixture_count": len(official.get("fixtures") or []),
    }


def _governance(
    snapshot,
    decision: dict,
    run: dict,
    acquisition: dict,
) -> dict:
    certification = decision.get("certification") or {}
    diagnostics = decision.get("provider_diagnostics") or {}
    return {
        "schema_version": 1,
        "exposure_class": ExposureClass.GOVERNANCE_PUBLIC.value,
        "season": run["season"],
        "target_gameweek": int(run["target_gameweek"]),
        "qualification_matrix": snapshot.read_json(
            "qualification_matrix.json"
        ),
        "certification": {
            "state": certification.get("state"),
            "actionable": certification.get("actionable"),
            "reasons": certification.get("reasons") or [],
            "warnings": certification.get("warnings") or [],
            "valid_until": certification.get("valid_until"),
        },
        "manager_actionability": _manager_actionability(acquisition, decision),
        "max_contiguous_qualified_horizon": diagnostics.get(
            "max_contiguous_horizon", 0
        ),
        "contingency_qualified_horizon": diagnostics.get(
            "contingency_qualified_horizon", 0
        ),
        "serving_provider_by_horizon": diagnostics.get(
            "serving_provider_by_horizon", {}
        ),
        "evidence_manifest": decision.get("evidence_manifest") or {},
    }


def _public_identity(
    snapshot,
    decision: dict,
    run: dict,
    canonical: dict,
) -> dict:
    manifest = decision.get("manifest") or {}
    return {
        "schema_version": 1,
        "season": run["season"],
        "target_gameweek": int(run["target_gameweek"]),
        "run_id": run["run_id"],
        "code_sha": run["code_sha"],
        "config_sha": run["config_sha"],
        "snapshot_id": snapshot.snapshot_id,
        "official_snapshot_sha256": _required_sha256(
            decision, "official_snapshot_hash"
        ),
        "canonical_projection_sha256": _required_sha256(
            decision, "canonical_projection_hash"
        ),
        "serving_provider_by_horizon": canonical[
            "serving_provider_by_horizon"
        ],
        "max_contiguous_qualified_horizon": canonical[
            "max_contiguous_qualified_horizon"
        ],
        "scoring_rules_version": canonical["scoring_rules_version"],
        "frozen_at": manifest.get("frozen_at")
        or snapshot.manifest.get("metadata", {}).get("frozen_at"),
    }


def _reveal_record(public_attempt_id: str, decision: dict, run: dict) -> dict:
    system = decision.get("system_decision")
    if system is None:
        return {
            "schema_version": 1,
            "public_attempt_id": public_attempt_id,
            "season": run["season"],
            "target_gameweek": int(run["target_gameweek"]),
            "decision_mode": "NO_DECISION",
            "transfers_in": [],
            "transfers_out": [],
            "xi_ids": [],
            "captain_id": None,
            "vice_captain_id": None,
            "bench_order": [],
            "objective": None,
            "horizon": 0,
            "transfer_hits": 0,
        }
    return {
        "schema_version": 1,
        "public_attempt_id": public_attempt_id,
        "season": run["season"],
        "target_gameweek": int(run["target_gameweek"]),
        "decision_mode": system.get("decision_mode"),
        "transfers_in": system.get("transfers_in") or [],
        "transfers_out": system.get("transfers_out") or [],
        "xi_ids": system.get("xi_ids") or [],
        "captain_id": system.get("captain_id"),
        "vice_captain_id": system.get("vice_captain_id"),
        "bench_order": system.get("bench_order") or [],
        "objective": system.get("objective"),
        "horizon": int(system.get("horizon") or 0),
        "transfer_hits": int(system.get("transfer_hits") or 0),
    }


def make_commitment(
    reveal: dict,
    *,
    key: bytes | None = None,
) -> tuple[dict, bytes]:
    key = key or secrets.token_bytes(32)
    if len(key) != 32:
        raise RuntimeError("commitment key must be exactly 256 bits")
    message = HMAC_DOMAIN_V1 + canonical_json_bytes(reveal)
    digest = hmac.new(key, message, hashlib.sha256).hexdigest()
    return {
        "schema_version": 1,
        "algorithm": "HMAC-SHA256",
        "domain": "apex-v2-private-decision-v1",
        "digest": digest,
    }, key


def verify_commitment(reveal: dict, commitment: dict, key: bytes) -> bool:
    expected, _ = make_commitment(reveal, key=key)
    return hmac.compare_digest(
        str(commitment.get("digest", "")),
        expected["digest"],
    )


def _private_attempt(
    public_attempt_id: str,
    decision: dict,
    team_state,
    run: dict,
    key: bytes,
    reveal: dict,
    canonical_forecast: dict,
) -> dict:
    transfer_plan = (
        (
            (decision.get("provider_diagnostics") or {}).get(
                "decision_optimisation"
            )
            or {}
        ).get("weeks")
        or []
    )
    canonical_forecast_sha256 = sha256_bytes(
        canonical_json_bytes(canonical_forecast)
    )
    private_identity = {
        "public_attempt_id": public_attempt_id,
        "team_state": team_state,
        "system_decision": decision.get("system_decision"),
        "transfer_plan": transfer_plan,
        "canonical_forecast_sha256": canonical_forecast_sha256,
    }
    private_attempt_id = sha256_bytes(canonical_json_bytes(private_identity))
    return {
        "schema_version": 2,
        "exposure_class": ExposureClass.PRIVATE_MANAGER.value,
        "private_attempt_id": private_attempt_id,
        "public_attempt_id": public_attempt_id,
        "season": run["season"],
        "target_gameweek": int(run["target_gameweek"]),
        "team_state": team_state,
        "system_decision": decision.get("system_decision"),
        "transfer_plan": transfer_plan,
        "canonical_forecast_sha256": canonical_forecast_sha256,
        "canonical_forecast": canonical_forecast,
        "reveal_record": reveal,
        "commitment_key_b64": base64.b64encode(key).decode("ascii"),
    }


def _write_attestation(
    path: Path,
    assets: dict[str, Path],
    *,
    public_attempt_id: str,
    scope: str,
) -> Path:
    payload = {
        "schema_version": 2,
        "scope": scope,
        "public_attempt_id": public_attempt_id,
        "assets": {
            name: sha256_file(asset)
            for name, asset in sorted(assets.items())
        },
    }
    return write_json(path, payload)


def verify_public_attestation(files: dict[str, Path]) -> dict:
    assert_exact_asset_set(
        files,
        PUBLIC_RELEASE_ASSETS_V1,
        "public release",
    )
    attestation = json.loads(
        Path(files["attestation.json"]).read_text(encoding="utf-8")
    )
    if attestation.get("scope") != "PUBLIC":
        raise RuntimeError("public attestation scope mismatch")
    expected = {
        name: sha256_file(path)
        for name, path in files.items()
        if name != "attestation.json"
    }
    if attestation.get("assets") != expected:
        raise RuntimeError("public attestation asset hashes do not match")
    return attestation


def build_publication_materials(
    snapshot_path: Path,
    decision_path: Path,
    output_dir: Path,
) -> PublicationMaterial:
    snapshot = open_frozen_snapshot(snapshot_path)
    decision = json.loads(Path(decision_path).read_text(encoding="utf-8"))
    run = snapshot.read_json("run.json")
    acquisition = _acquisition(snapshot)
    mode, credential_present = _manager_state_mode(acquisition)
    _assert_public_transfer_ledger(acquisition)

    public_dir = Path(output_dir) / "public"
    private_dir = Path(output_dir) / "private"
    diagnostics_dir = Path(output_dir) / "diagnostics"
    for directory in (public_dir, private_dir, diagnostics_dir):
        directory.mkdir(parents=True, exist_ok=True)

    private_canonical = _canonical_forecast(snapshot, decision, run)
    canonical = _canonical_forecast_commitment(private_canonical)
    governance = _governance(snapshot, decision, run, acquisition)
    evidence = {
        "schema_version": 1,
        "exposure_class": ExposureClass.PUBLIC_RESEARCH.value,
        "rows": _sanitize_public_evidence(
            snapshot.read_json("evidence.json")
        ),
    }
    identity = _public_identity(snapshot, decision, run, canonical)
    public_attempt_id = sha256_bytes(canonical_json_bytes(identity))

    commitment = None
    private_files: dict[str, Path] = {}
    private_attempt_id = None
    if mode == AUTHENTICATED_MODE:
        team_state = snapshot.read_json("team_state.json")
        if not team_state:
            raise RuntimeError(
                "authenticated acquisition has no manager TeamState"
            )
        reveal = _reveal_record(public_attempt_id, decision, run)
        commitment, key = make_commitment(reveal)
        commitment["reveal_not_before"] = run["deadline"]
        commitment["public_attempt_id"] = public_attempt_id
        private_payload = _private_attempt(
            public_attempt_id,
            decision,
            team_state,
            run,
            key,
            reveal,
            private_canonical,
        )
        if (
            private_payload["canonical_forecast_sha256"]
            != canonical["private_canonical_forecast_sha256"]
        ):
            raise RuntimeError(
                "private canonical forecast does not match public commitment"
            )
        private_attempt_id = private_payload["private_attempt_id"]
        private_path = write_json(
            private_dir / "private_manager_attempt.json",
            private_payload,
        )
        private_attestation = _write_attestation(
            private_dir / "private_attestation.json",
            {"private_manager_attempt.json": private_path},
            public_attempt_id=public_attempt_id,
            scope="PRIVATE_MANAGER",
        )
        private_files = {
            "private_manager_attempt.json": private_path,
            "private_attestation.json": private_attestation,
        }
        assert_exact_asset_set(
            private_files,
            PRIVATE_RELEASE_ASSETS_V1,
            "private release",
        )

    public_attempt = {
        **identity,
        "public_attempt_id": public_attempt_id,
        "exposure_class": ExposureClass.PUBLIC_CANONICAL.value,
        "private_decision_commitment": commitment,
        "certification": governance["certification"],
        "manager_actionability": governance["manager_actionability"],
    }
    public_attempt_path = write_json(
        public_dir / "public_attempt.json",
        public_attempt,
    )
    canonical_path = write_json(
        public_dir / "canonical_forecast.json",
        canonical,
    )
    archive_path, archive_entries = _provider_forecast_archive(
        snapshot,
        public_dir / "provider_forecasts.tar.gz",
    )
    governance["provider_archive_entries"] = archive_entries
    governance_path = write_json(
        public_dir / "governance.json",
        governance,
    )
    evidence_path = write_json(public_dir / "evidence.json", evidence)
    non_attested = {
        "public_attempt.json": public_attempt_path,
        "canonical_forecast.json": canonical_path,
        "provider_forecasts.tar.gz": archive_path,
        "governance.json": governance_path,
        "evidence.json": evidence_path,
    }
    attestation_path = _write_attestation(
        public_dir / "attestation.json",
        non_attested,
        public_attempt_id=public_attempt_id,
        scope="PUBLIC",
    )
    public_files = {**non_attested, "attestation.json": attestation_path}
    assert_exact_asset_set(
        public_files,
        PUBLIC_RELEASE_ASSETS_V1,
        "public release",
    )
    verify_public_attestation(public_files)

    summary = write_json(
        diagnostics_dir / "publication_summary.json",
        {
            "schema_version": 1,
            "run_id": run["run_id"],
            "season": run["season"],
            "target_gameweek": int(run["target_gameweek"]),
            "public_attempt_id": public_attempt_id,
            "public_asset_names": sorted(PUBLIC_RELEASE_ASSETS_V1),
            "private_store_required": bool(credential_present),
            "manager_actionability": governance["manager_actionability"],
            "canonical_publication_contract": canonical["content_contract"],
        },
    )
    diagnostics_files = {
        "public_attempt.json": write_json(
            diagnostics_dir / "public_attempt.json",
            public_attempt,
        ),
        "governance.json": write_json(
            diagnostics_dir / "governance.json",
            governance,
        ),
        "attestation.json": write_json(
            diagnostics_dir / "attestation.json",
            json.loads(attestation_path.read_text(encoding="utf-8")),
        ),
        "publication_summary.json": summary,
    }
    assert_exact_asset_set(
        diagnostics_files,
        DIAGNOSTIC_ARTIFACT_ASSETS_V1,
        "diagnostic artifact",
    )

    return PublicationMaterial(
        public_files=public_files,
        private_files=private_files,
        diagnostics_files=diagnostics_files,
        public_attempt_id=public_attempt_id,
        private_attempt_id=private_attempt_id,
        authenticated_manager_state=(mode == AUTHENTICATED_MODE),
    )
