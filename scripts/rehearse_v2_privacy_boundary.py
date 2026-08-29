from __future__ import annotations

import json
import os
import secrets
import tarfile
from pathlib import Path

from apex.runtime.acquire import assert_private_manager_credential_opt_in
from apex.runtime.publication import (
    DIAGNOSTIC_ARTIFACT_ASSETS_V1,
    PRIVATE_RELEASE_ASSETS_V1,
    PUBLIC_RELEASE_ASSETS_V1,
    build_publication_materials,
)
from apex.runtime.reveal import verify_private_payload_reveal
from apex.runtime.snapshot import SnapshotBuilder

SEASON = "2026-2027"
TARGET_GAMEWEEK = 3
DEADLINE = "2026-09-12T10:00:00+00:00"
OFFICIAL_HASH = "a" * 64
CANONICAL_HASH = "b" * 64


def _json(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return path


def _provider_surface(sentinel: str) -> dict:
    return {
        "schema_version": 1,
        "provider_id": "airsenal",
        "provider_version": "privacy-rehearsal-v1",
        "generated_at": "2026-09-01T10:00:00+00:00",
        "season": SEASON,
        "source_snapshot": OFFICIAL_HASH,
        "scoring_rules_version": SEASON,
        "supported_horizons": [1],
        "runtime_dependencies": [],
        "rows": [
            {
                "element_id": element_id,
                "gameweek": TARGET_GAMEWEEK,
                "horizon": 1,
                "expected_points": float(2 + element_id / 100),
                "fixture_ids": [1000 + element_id],
                "n_fixtures": 1,
                "player_status_at_forecast": "a",
                "expected_minutes": 90.0,
                "p_appearance": 1.0,
                "p_start": 1.0,
                "p_60": 1.0,
                "coverage_status": "FORECAST",
                "coverage_reason": None,
                "metadata": {
                    "privacy_sentinel": sentinel,
                    "must_never_cross_public_boundary": True,
                },
            }
            for element_id in range(1, 21)
        ],
    }


def _build_snapshot(base: Path, sentinel: str) -> Path:
    team_state = {
        "schema_version": 1,
        "entry_id": 63984,
        "published_gw": 2,
        "squad_ids": list(range(1, 16)),
        "bank_tenths": 7,
        "free_transfers": 2,
        "purchase_prices_tenths": {str(i): 50 for i in range(1, 16)},
        "selling_prices_tenths": {str(i): 50 for i in range(1, 16)},
        "active_chip": None,
        "state_complete_for_transfers": True,
        "privacy_sentinel": sentinel,
    }
    acquisition = {
        "schema_version": 1,
        "mode": "AUTHENTICATED_MY_TEAM",
        "credential_present": True,
        "target_gameweek": TARGET_GAMEWEEK,
        "published_gw": 2,
        "state_complete_for_transfers": True,
        "purchase_price_count": 15,
        "selling_price_count": 15,
        "public_transfer_ledger": {
            "available": True,
            "row_count": 0,
            "events": [],
            "last_visible_event": None,
            "target_gameweek_row_count": 0,
            "sha256": "0" * 64,
            "error": None,
            "visibility_contract": "OWNER_AUTHENTICATED_CURRENT_STATE",
        },
        "detail": "synthetic privacy-boundary rehearsal",
    }
    run = {
        "schema_version": 1,
        "run_id": "privacy-rehearsal",
        "code_sha": os.getenv("GITHUB_SHA", "privacy-rehearsal-sha"),
        "config_sha": "config-rehearsal-hash",
        "run_started_at": "2026-09-01T09:59:00+00:00",
        "acquired_at": "2026-09-01T10:00:00+00:00",
        "frozen_at": "2026-09-01T10:00:01+00:00",
        "target_gameweek": TARGET_GAMEWEEK,
        "season": SEASON,
        "entry_id": 63984,
        "max_horizon": 1,
        "scoring_rules_version": SEASON,
        "deadline": DEADLINE,
        "team_state_mode": "AUTHENTICATED_MY_TEAM",
        "team_state_complete_for_transfers": True,
    }
    matrix = [
        {
            "provider_id": "airsenal",
            "role": "CHAMPION",
            "priority": 0,
            "health": "HEALTHY",
            "qualification_by_horizon": {"1": "QUALIFIED"},
            "reasons": [],
            "serve_authorized": True,
            "predictive_status": "QUALIFIED",
            "scoring_rules_version": SEASON,
        }
    ]

    builder = SnapshotBuilder()
    builder.add_json(
        "official.json",
        {"schema_version": 1, "source_hash": OFFICIAL_HASH},
    )
    builder.add_json("team_state.json", team_state)
    builder.add_json("team_state_acquisition.json", acquisition)
    builder.add_json("team_transfers_public.json", [])
    builder.add_json("evidence.json", [])
    builder.add_json("evidence_validation.json", {"errors": []})
    builder.add_json("qualification_matrix.json", matrix)
    builder.add_json("providers/airsenal.json", _provider_surface(sentinel))
    builder.add_json("run.json", run)
    builder.add_bytes("config.yaml", b"privacy_rehearsal: true\n")
    return builder.freeze(
        base / "snapshots",
        metadata={"frozen_at": run["frozen_at"]},
    ).root


def _build_decision(path: Path, sentinel: str) -> Path:
    payload = {
        "schema_version": 1,
        "manifest": {
            "schema_version": 1,
            "run_id": "privacy-rehearsal",
            "season": SEASON,
            "target_gameweek": TARGET_GAMEWEEK,
            "code_sha": os.getenv("GITHUB_SHA", "privacy-rehearsal-sha"),
            "config_sha": "config-rehearsal-hash",
            "frozen_at": "2026-09-01T10:00:01+00:00",
            "serving_provider_by_horizon": {"1": "airsenal"},
        },
        "official_snapshot_hash": OFFICIAL_HASH,
        "canonical_projection_hash": CANONICAL_HASH,
        "system_decision": {
            "schema_version": 1,
            "squad_ids": list(range(1, 16)),
            "xi_ids": list(range(1, 12)),
            "captain_id": 1,
            "vice_captain_id": 2,
            "bench_order": [12, 13, 14, 15],
            "transfers_in": [16],
            "transfers_out": [15],
            "objective": 61.25,
            "horizon": 1,
            "transfer_hits": 0,
            "decision_mode": "TRANSFER_HORIZON",
            "privacy_sentinel": sentinel,
        },
        "certification": {
            "schema_version": 1,
            "state": "CERTIFIED",
            "actionable": True,
            "reasons": [],
            "warnings": [],
            "valid_until": DEADLINE,
        },
        "provider_diagnostics": {
            "max_contiguous_horizon": 1,
            "serving_provider_by_horizon": {"1": "airsenal"},
        },
        "evidence_manifest": {
            "hard_evidence_count": 0,
            "validation_errors": [],
        },
    }
    return _json(path, payload)


def _assert_no_sentinel(root: Path, sentinel: str) -> None:
    needle = sentinel.encode("utf-8")
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffixes[-2:] == [".tar", ".gz"] or path.name.endswith(
            ".tar.gz"
        ):
            with tarfile.open(path, "r:gz") as archive:
                for member in archive.getmembers():
                    if not member.isfile():
                        continue
                    handle = archive.extractfile(member)
                    if handle and needle in handle.read():
                        raise AssertionError(
                            "privacy sentinel leaked inside archive member "
                            f"{member.name}"
                        )
        elif needle in path.read_bytes():
            raise AssertionError(f"privacy sentinel leaked into {path}")


def _assert_forbidden_manager_fields(root: Path) -> None:
    forbidden = (
        b'"squad_ids"',
        b'"purchase_prices_tenths"',
        b'"selling_prices_tenths"',
        b'"bank_tenths"',
        b'"free_transfers"',
        b'"transfers_in"',
        b'"transfers_out"',
        b'"captain_id"',
        b'"vice_captain_id"',
    )
    for path in root.rglob("*"):
        if not path.is_file() or path.name.endswith(".tar.gz"):
            continue
        data = path.read_bytes()
        found = [field.decode() for field in forbidden if field in data]
        if found:
            raise AssertionError(
                f"manager-only fields leaked into {path.name}: {found}"
            )


def main() -> int:
    sentinel = os.getenv("APEX_PRIVACY_SENTINEL") or secrets.token_urlsafe(36)
    output = Path(
        os.getenv(
            "APEX_PRIVACY_REHEARSAL_DIR",
            "artifacts/v2/privacy-rehearsal",
        )
    )
    output.mkdir(parents=True, exist_ok=True)

    # Exercise the source-level fake-credential gate without making any network call.
    os.environ["FPL_SESSION_COOKIE"] = "fake-session-for-privacy-rehearsal"
    os.environ["FPL_X_API_AUTHORIZATION"] = "fake-token-for-privacy-rehearsal"
    os.environ["APEX_ENABLE_PRIVATE_MANAGER_STATE"] = "1"
    assert_private_manager_credential_opt_in()

    snapshot = _build_snapshot(output, sentinel)
    decision = _build_decision(output / "decision_bundle.json", sentinel)
    material = build_publication_materials(
        snapshot,
        decision,
        output / "publication",
    )

    assert material.authenticated_manager_state
    assert frozenset(material.public_files) == PUBLIC_RELEASE_ASSETS_V1
    assert frozenset(material.private_files) == PRIVATE_RELEASE_ASSETS_V1
    assert frozenset(material.diagnostics_files) == DIAGNOSTIC_ARTIFACT_ASSETS_V1

    private_bytes = b"".join(
        path.read_bytes() for path in material.private_files.values()
    )
    assert sentinel.encode("utf-8") in private_bytes
    _assert_no_sentinel(output / "publication" / "public", sentinel)
    _assert_no_sentinel(output / "publication" / "diagnostics", sentinel)
    _assert_forbidden_manager_fields(output / "publication" / "public")
    _assert_forbidden_manager_fields(output / "publication" / "diagnostics")

    provider_archive = material.public_files["provider_forecasts.tar.gz"]
    with tarfile.open(provider_archive, "r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            payload = json.loads(archive.extractfile(member).read())
            assert all(
                row.get("metadata") == {}
                for row in payload.get("rows", [])
            )

    public_attempt = json.loads(
        material.public_files["public_attempt.json"].read_text(encoding="utf-8")
    )
    assert public_attempt["official_snapshot_sha256"] == OFFICIAL_HASH
    assert public_attempt["canonical_projection_sha256"] == CANONICAL_HASH
    actionability = public_attempt["manager_actionability"]
    assert actionability["manager_state_scope"] == "FULL_MANAGER"
    assert actionability["personalized_actionable"] is True
    assert actionability["transfer_actionable"] is True

    private_payload = json.loads(
        material.private_files["private_manager_attempt.json"].read_text(
            encoding="utf-8"
        )
    )
    assert not verify_private_payload_reveal(
        private_payload=private_payload,
        public_attempt=public_attempt,
        now="2026-09-12T09:59:59+00:00",
    )
    assert verify_private_payload_reveal(
        private_payload=private_payload,
        public_attempt=public_attempt,
        now="2026-09-12T10:00:00+00:00",
    )

    # Never print the sentinel or fake credentials. This line is intentionally
    # limited to public identity so Actions logs themselves are rehearsal-safe.
    print(f"PASS public_attempt_id={material.public_attempt_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
