from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from apex.domain.models import (
    CoverageStatus,
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    ProjectionRow,
    ProjectionSurface,
    TeamState,
    dataclass_to_dict,
)
from apex.runtime.publication import replay_security_payload
from apex.runtime.publication_impl import canonical_json_bytes
from apex.runtime.snapshot import SnapshotBuilder, open_frozen_snapshot
from apex.runtime.solve import solve_snapshot

REPLAY_NOW = datetime(2026, 9, 3, 7, 0, tzinfo=timezone.utc)


def _digest(value) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _players() -> tuple[OfficialPlayer, ...]:
    players = []
    player_id = 1
    specs = [
        (Position.GK, (1, 2)),
        (Position.DEF, (1, 2, 3, 4, 5)),
        (Position.MID, (3, 4, 5, 6, 7)),
        (Position.FWD, (6, 7, 8)),
    ]
    for position, team_ids in specs:
        for team_id in team_ids:
            players.append(
                OfficialPlayer(
                    player_id,
                    f"P{player_id}",
                    team_id,
                    position,
                    50,
                    "a",
                    True,
                    10_000 + player_id,
                )
            )
            player_id += 1
    for position in Position:
        for index in range(4):
            players.append(
                OfficialPlayer(
                    player_id,
                    f"A{player_id}",
                    9 + index,
                    position,
                    50,
                    "a",
                    True,
                    10_000 + player_id,
                )
            )
            player_id += 1
    return tuple(players)


def _surface(official: OfficialSnapshot, horizons: int) -> ProjectionSurface:
    rows = []
    for player in official.players:
        for horizon in range(1, horizons + 1):
            rows.append(
                ProjectionRow(
                    player.element_id,
                    2 + horizon - 1,
                    horizon,
                    10.0 if player.element_id > 15 else 3.0,
                    expected_minutes=90.0,
                    p_appearance=1.0,
                    p_start=1.0,
                    p_60=1.0,
                    coverage_status=CoverageStatus.FORECAST,
                )
            )
    return ProjectionSurface(
        1,
        "airsenal",
        "golden-v1",
        "2026-09-03T06:30:00Z",
        official.season,
        official.source_hash,
        "fpl-2026-27-v1",
        tuple(range(1, horizons + 1)),
        (),
        tuple(rows),
    )


def _freeze(root: Path, run_id: str, horizons: int, team: TeamState | None):
    official = OfficialSnapshot(
        1,
        "2026-2027",
        "2026-09-03T06:00:00Z",
        "golden-official-hash",
        _players(),
        (),
        {2: "2026-09-12T10:00:00Z", 3: "2026-09-19T10:00:00Z"},
    )
    surface = _surface(official, horizons)
    builder = SnapshotBuilder()
    builder.add_json("official.json", dataclass_to_dict(official))
    builder.add_json("official_raw.json", {"teams": []})
    builder.add_json("team_state.json", dataclass_to_dict(team) if team else None)
    builder.add_json("evidence.json", [])
    builder.add_json("evidence_validation.json", {"errors": []})
    builder.add_json("providers/airsenal.json", dataclass_to_dict(surface))
    builder.add_json(
        "qualification_matrix.json",
        [
            {
                "provider_id": "airsenal",
                "role": "CHAMPION",
                "priority": 0,
                "health": "HEALTHY",
                "qualification_by_horizon": {
                    str(h): "QUALIFIED" for h in range(1, horizons + 1)
                },
                "reasons": [],
                "serve_authorized": True,
                "predictive_status": "INSUFFICIENT_HISTORY",
            }
        ],
    )
    builder.add_json(
        "run.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "code_sha": "golden-code",
            "config_sha": "golden-config",
            "run_started_at": "2026-09-03T06:00:00Z",
            "acquired_at": "2026-09-03T06:30:00Z",
            "target_gameweek": 2,
            "season": official.season,
            "entry_id": 63984,
            "max_horizon": horizons,
            "deadline": "2026-09-12T10:00:00Z",
            "evidence_required": False,
        },
    )
    builder.add_bytes(
        "config.yaml",
        b"schema_version: 1\nmax_horizon: 2\nproviders:\n  - id: airsenal\n    max_age_hours: 48\n",
    )
    return builder.freeze(root, metadata={"fixture": run_id})


def _assert_replay(snapshot, tmp_path: Path, snapshot_id: str, semantic_digest: str):
    assert snapshot.snapshot_id == snapshot_id
    assert open_frozen_snapshot(snapshot.root).snapshot_id == snapshot_id
    first = solve_snapshot(snapshot.root, tmp_path / "first.json", now=REPLAY_NOW)
    second = solve_snapshot(snapshot.root, tmp_path / "second.json", now=REPLAY_NOW)
    first_dict = dataclass_to_dict(first)
    second_dict = dataclass_to_dict(second)
    first_semantic = replay_security_payload(first_dict)
    second_semantic = replay_security_payload(second_dict)
    assert canonical_json_bytes(first_dict) == canonical_json_bytes(second_dict)
    assert canonical_json_bytes(first_semantic) == canonical_json_bytes(second_semantic)
    actual_digest = _digest(first_semantic)
    assert actual_digest == semantic_digest, f"semantic replay digest: {actual_digest}"
    assert json.loads((tmp_path / "first.json").read_text()) == first_dict
    assert json.loads((tmp_path / "second.json").read_text()) == second_dict
    return first


def test_golden_initial_squad_replay_is_semantically_stable(tmp_path: Path):
    snapshot = _freeze(tmp_path / "initial-snapshots", "golden-initial", 1, None)
    bundle = _assert_replay(
        snapshot,
        tmp_path,
        "900f15529a89c680b0be61b485ad62c9a8661597d3191317dfa4b6c5b66cf699",
        "e2a8ef2b1c38db557b479825f12f559f9c190d4fc9ffccac504e736beedb4151",
    )
    assert bundle.system_decision is not None
    assert bundle.system_decision.decision_mode == "INITIAL_SQUAD"


def test_golden_transfer_horizon_replay_is_semantically_stable(tmp_path: Path):
    squad = tuple(range(1, 16))
    team = TeamState(
        1,
        63984,
        1,
        squad,
        0,
        1,
        {player_id: 50 for player_id in squad},
        {player_id: 50 for player_id in squad},
        None,
        True,
    )
    snapshot = _freeze(tmp_path / "transfer-snapshots", "golden-transfer", 2, team)
    bundle = _assert_replay(
        snapshot,
        tmp_path,
        "e17a1a00688fc2242dca58c1beb990fd2024f1164f61e66520c5d72c6a9cf52c",
        "9e762d18ac09a8db341eee0a8d6ccf7625b56a0ee8dfe65f89bade26dc51f015",
    )
    assert bundle.system_decision is not None
    assert bundle.system_decision.decision_mode == "TRANSFER_HORIZON"
    assert bundle.provider_diagnostics["decision_optimisation"]["status"] == "OPTIMAL"


def test_workflow_run_id_changes_only_execution_metadata(tmp_path: Path, monkeypatch):
    snapshot = _freeze(tmp_path / "run-id-snapshots", "golden-run-id", 1, None)

    monkeypatch.setenv("GITHUB_RUN_ID", "111")
    first = dataclass_to_dict(
        solve_snapshot(snapshot.root, tmp_path / "run-a.json", now=REPLAY_NOW)
    )
    monkeypatch.setenv("GITHUB_RUN_ID", "222")
    second = dataclass_to_dict(
        solve_snapshot(snapshot.root, tmp_path / "run-b.json", now=REPLAY_NOW)
    )

    assert first["manifest"]["workflow_run_id"] == "111"
    assert second["manifest"]["workflow_run_id"] == "222"
    assert canonical_json_bytes(first) != canonical_json_bytes(second)
    assert canonical_json_bytes(replay_security_payload(first)) == canonical_json_bytes(
        replay_security_payload(second)
    )
