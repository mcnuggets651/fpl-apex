from datetime import datetime, timezone
from pathlib import Path
import json

from apex.decision.transfers import TransferOptimisationResult
from apex.domain.models import (
    CoverageStatus,
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    ProjectionRow,
    ProjectionSurface,
    ReasonCode,
    TeamState,
    dataclass_to_dict,
)
from apex.runtime.snapshot import SnapshotBuilder
from apex.runtime.solve import solve_snapshot

TEST_NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def synthetic_official():
    players = []
    pid = 1
    for team in range(1, 8):
        for position, count in (
            (Position.GK, 1),
            (Position.DEF, 2),
            (Position.MID, 2),
            (Position.FWD, 1),
        ):
            for _ in range(count):
                players.append(
                    OfficialPlayer(pid, f"P{pid}", team, position, 45, "a", True)
                )
                pid += 1
    return OfficialSnapshot(
        1,
        "2026-2027",
        "2026-08-28T10:00:00Z",
        "official-hash",
        tuple(players),
        (),
        {2: "2026-08-29T10:00:00Z"},
    )


def test_frozen_snapshot_solves_without_source_layer(tmp_path: Path, monkeypatch):
    official = synthetic_official()
    rows = tuple(
        ProjectionRow(
            p.element_id,
            2,
            1,
            float(p.element_id % 10 + 1),
            p_appearance=1.0,
            coverage_status=CoverageStatus.FORECAST,
        )
        for p in official.players
    )
    surface = ProjectionSurface(
        1,
        "airsenal",
        "v1",
        "2026-08-28T10:05:00Z",
        official.season,
        official.source_hash,
        "2026-2027",
        (1,),
        (),
        rows,
    )
    builder = SnapshotBuilder()
    builder.add_json("official.json", dataclass_to_dict(official))
    builder.add_json("team_state.json", None)
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
                "qualification_by_horizon": {"1": "QUALIFIED"},
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
            "run_id": "r1",
            "code_sha": "abc",
            "config_sha": "cfg",
            "run_started_at": "2026-08-28T10:00:00Z",
            "acquired_at": "2026-08-28T10:05:00Z",
            "target_gameweek": 2,
            "season": official.season,
            "entry_id": 1,
            "max_horizon": 1,
            "deadline": "2026-08-29T10:00:00Z",
        },
    )
    builder.add_bytes("config.yaml", b"x: y\n")
    snapshot = builder.freeze(tmp_path / "snapshots")
    output = tmp_path / "decision.json"
    import socket

    def deny_network(*args, **kwargs):
        raise AssertionError("network attempted during frozen solve")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    bundle = solve_snapshot(snapshot.root, output, now=TEST_NOW)
    assert bundle.certification.actionable
    assert bundle.system_decision is not None
    assert len(bundle.system_decision.squad_ids) == 15
    assert json.loads(output.read_text())["certification"]["actionable"] is True


def test_infeasible_transfer_is_persisted_as_blocked_diagnostic(
    tmp_path: Path,
    monkeypatch,
):
    official = synthetic_official()
    squad = tuple(player.element_id for player in official.players[:15])
    team = TeamState(
        1,
        1,
        1,
        squad,
        0,
        1,
        {player_id: 45 for player_id in squad},
        {player_id: 45 for player_id in squad},
        None,
        True,
    )
    rows = []
    for player in official.players:
        rows.extend(
            [
                ProjectionRow(
                    player.element_id,
                    2,
                    1,
                    3.0,
                    coverage_status=CoverageStatus.FORECAST,
                ),
                ProjectionRow(
                    player.element_id,
                    3,
                    2,
                    3.0,
                    coverage_status=CoverageStatus.FORECAST,
                ),
            ]
        )
    surface = ProjectionSurface(
        1,
        "airsenal",
        "v1",
        "2026-08-28T10:05:00Z",
        official.season,
        official.source_hash,
        "2026-2027",
        (1, 2),
        (),
        tuple(rows),
    )
    builder = SnapshotBuilder()
    builder.add_json("official.json", dataclass_to_dict(official))
    builder.add_json("team_state.json", dataclass_to_dict(team))
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
                    "1": "QUALIFIED",
                    "2": "QUALIFIED",
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
            "run_id": "r-infeasible",
            "code_sha": "abc",
            "config_sha": "cfg",
            "run_started_at": "2026-08-28T10:00:00Z",
            "acquired_at": "2026-08-28T10:05:00Z",
            "target_gameweek": 2,
            "season": official.season,
            "entry_id": 1,
            "max_horizon": 2,
            "deadline": "2026-08-29T10:00:00Z",
        },
    )
    builder.add_bytes("config.yaml", b"x: y\n")
    snapshot = builder.freeze(tmp_path / "snapshots")
    output = tmp_path / "decision.json"

    called = {}

    def infeasible(*args, **kwargs):
        called.update(kwargs)
        return TransferOptimisationResult(
            None,
            (),
            "INFEASIBLE",
            None,
            {"message": "synthetic solver infeasible"},
        )

    monkeypatch.setattr(
        "apex.runtime.solve.optimise_transfer_horizon",
        infeasible,
    )
    bundle = solve_snapshot(snapshot.root, output, now=TEST_NOW)
    diagnostics = bundle.provider_diagnostics["decision_optimisation"]

    assert called["candidate_limit"] == 1
    assert bundle.certification.actionable is False
    assert bundle.certification.state.value == "BLOCKED"
    assert ReasonCode.DECISION_ILLEGAL in bundle.certification.reasons
    assert diagnostics["kind"] == "TRANSFER_HORIZON"
    assert diagnostics["status"] == "INFEASIBLE"
    assert diagnostics["solver"]["message"] == "synthetic solver infeasible"
    assert any(
        warning == "transfer optimiser infeasible: synthetic solver infeasible"
        for warning in bundle.certification.warnings
    )

    persisted = json.loads(output.read_text())
    assert (
        persisted["provider_diagnostics"]["decision_optimisation"]["status"]
        == "INFEASIBLE"
    )
    assert "DECISION_ILLEGAL" in persisted["certification"]["reasons"]
