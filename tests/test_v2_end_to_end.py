from pathlib import Path
import json

from apex.domain.models import (
    CoverageStatus,
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    ProjectionRow,
    ProjectionSurface,
    dataclass_to_dict,
)
from apex.runtime.snapshot import SnapshotBuilder
from apex.runtime.solve import solve_snapshot


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
    bundle = solve_snapshot(snapshot.root, output)
    assert bundle.certification.actionable
    assert bundle.system_decision is not None
    assert len(bundle.system_decision.squad_ids) == 15
    assert json.loads(output.read_text())["certification"]["actionable"] is True
