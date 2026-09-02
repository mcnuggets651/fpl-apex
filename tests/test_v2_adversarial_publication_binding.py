from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from apex.runtime.publication import build_publication_materials
from apex.runtime.snapshot import SnapshotBuilder


def _fixture(tmp_path: Path):
    official_hash = "a" * 64
    builder = SnapshotBuilder()
    builder.add_json(
        "official.json",
        {
            "schema_version": 1,
            "season": "2026-2027",
            "acquired_at": "2026-09-02T12:00:00Z",
            "source_hash": official_hash,
            "players": [],
            "fixtures": [],
            "deadlines": {"3": "2026-09-12T10:00:00Z"},
        },
    )
    builder.add_json("official_raw.json", {"teams": []})
    builder.add_json(
        "run.json",
        {
            "schema_version": 1,
            "run_id": "run-123",
            "code_sha": "code-abc",
            "config_sha": "config-abc",
            "run_started_at": "2026-09-02T11:59:00Z",
            "acquired_at": "2026-09-02T12:00:00Z",
            "frozen_at": "2026-09-02T12:01:00Z",
            "target_gameweek": 3,
            "season": "2026-2027",
            "entry_id": 63984,
            "max_horizon": 1,
            "scoring_rules_version": "fpl-2026-27-v1",
            "deadline": "2026-09-12T10:00:00Z",
            "evidence_required": False,
        },
    )
    builder.add_json(
        "team_state_acquisition.json",
        {
            "mode": "PUBLIC_DEADLINE_FALLBACK",
            "credential_present": False,
            "state_complete_for_transfers": False,
            "target_gameweek": 3,
            "public_transfer_ledger": {
                "target_gameweek_row_count": 0,
                "last_visible_event": 2,
                "events": [1, 2],
            },
        },
    )
    builder.add_json("team_state.json", None)
    builder.add_json("qualification_matrix.json", [])
    builder.add_json("evidence.json", [])
    builder.add_json(
        "providers/airsenal.json",
        {
            "schema_version": 1,
            "provider_id": "airsenal",
            "provider_version": "pinned",
            "generated_at": "2026-09-02T12:00:00Z",
            "season": "2026-2027",
            "source_snapshot": official_hash,
            "scoring_rules_version": "fpl-2026-27-v1",
            "supported_horizons": [1],
            "runtime_dependencies": [],
            "rows": [],
        },
    )
    snapshot = builder.freeze(
        tmp_path / "snapshots",
        metadata={"frozen_at": "2026-09-02T12:01:00Z"},
    )
    decision = {
        "schema_version": 1,
        "manifest": {
            "schema_version": 1,
            "run_id": "run-123",
            "workflow_run_id": None,
            "season": "2026-2027",
            "target_gameweek": 3,
            "code_sha": "code-abc",
            "config_sha": "config-abc",
            "acquired_at": "2026-09-02T12:00:00Z",
            "snapshot_id": snapshot.snapshot_id,
            "serving_provider_by_horizon": {"1": "airsenal"},
            "started_at": "2026-09-02T11:59:00Z",
            "frozen_at": "2026-09-02T12:01:00Z",
        },
        "official_snapshot_hash": official_hash,
        # Deliberately only a syntactically valid digest; current publication must
        # prove it actually matches the canonical surface reconstructed from snapshot.
        "canonical_projection_hash": "b" * 64,
        "system_decision": None,
        "certification": {
            "schema_version": 1,
            "state": "BLOCKED",
            "actionable": False,
            "reasons": ["DECISION_ILLEGAL"],
            "warnings": [],
            "valid_until": "2026-09-12T10:00:00Z",
        },
        "provider_diagnostics": {
            "max_contiguous_horizon": 1,
            "serving_provider_by_horizon": {"1": "airsenal"},
            "decision_optimisation": {
                "kind": "NONE",
                "status": "NOT_RUN",
                "solver": {},
                "weeks": [],
            },
        },
        "evidence_manifest": {},
    }
    decision_path = tmp_path / "decision.json"
    decision_path.write_text(json.dumps(decision), encoding="utf-8")
    return snapshot, decision, decision_path


def _publish(tmp_path: Path, snapshot, decision: dict):
    decision_path = tmp_path / "decision-mutated.json"
    decision_path.write_text(json.dumps(decision), encoding="utf-8")
    return build_publication_materials(
        snapshot.root,
        decision_path,
        tmp_path / "publication",
    )


def test_publication_rejects_decision_from_different_snapshot(tmp_path: Path):
    snapshot, decision, _ = _fixture(tmp_path)
    changed = deepcopy(decision)
    changed["manifest"]["snapshot_id"] = "f" * 64
    with pytest.raises(RuntimeError, match="snapshot"):
        _publish(tmp_path, snapshot, changed)


def test_publication_rejects_decision_run_identity_mismatch(tmp_path: Path):
    snapshot, decision, _ = _fixture(tmp_path)
    for field, value in (
        ("run_id", "other-run"),
        ("season", "2025-2026"),
        ("target_gameweek", 4),
        ("code_sha", "other-code"),
        ("config_sha", "other-config"),
    ):
        changed = deepcopy(decision)
        changed["manifest"][field] = value
        with pytest.raises(RuntimeError, match=field.replace("_", ".*")):
            _publish(tmp_path, snapshot, changed)


def test_publication_rejects_official_hash_not_bound_to_snapshot(tmp_path: Path):
    snapshot, decision, _ = _fixture(tmp_path)
    changed = deepcopy(decision)
    changed["official_snapshot_hash"] = "c" * 64
    with pytest.raises(RuntimeError, match="official.*hash|hash.*official"):
        _publish(tmp_path, snapshot, changed)


def test_publication_rejects_fake_canonical_projection_hash(tmp_path: Path):
    snapshot, decision, _ = _fixture(tmp_path)
    with pytest.raises(RuntimeError, match="canonical.*hash|hash.*canonical"):
        _publish(tmp_path, snapshot, decision)
