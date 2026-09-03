from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from apex.domain.models import (
    CoverageStatus,
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    ProjectionRow,
    ProjectionSurface,
    ReasonCode,
    dataclass_to_dict,
)
from apex.runtime.snapshot import SnapshotBuilder
from apex.runtime.solve import solve_snapshot


def _official() -> OfficialSnapshot:
    players = []
    player_id = 1
    for team_id in range(1, 8):
        for position, count in (
            (Position.GK, 1),
            (Position.DEF, 2),
            (Position.MID, 2),
            (Position.FWD, 1),
        ):
            for _ in range(count):
                players.append(
                    OfficialPlayer(
                        player_id,
                        f"P{player_id}",
                        team_id,
                        position,
                        45,
                        "a",
                        True,
                    )
                )
                player_id += 1
    return OfficialSnapshot(
        1,
        "2026-2027",
        "2026-09-02T10:00:00Z",
        "official-hash",
        tuple(players),
        (),
        {3: "2026-09-02T18:00:00Z"},
    )


def test_solve_rechecks_provider_freshness_against_frozen_sla(tmp_path: Path):
    official = _official()
    surface = ProjectionSurface(
        1,
        "airsenal",
        "v1",
        "2026-09-02T10:05:00Z",
        official.season,
        official.source_hash,
        "fpl-2026-27-v1",
        (1,),
        (),
        tuple(
            ProjectionRow(
                player.element_id,
                3,
                1,
                float(player.element_id % 10 + 1),
                p_appearance=1.0,
                coverage_status=CoverageStatus.FORECAST,
            )
            for player in official.players
        ),
    )

    builder = SnapshotBuilder()
    builder.add_json("official.json", dataclass_to_dict(official))
    builder.add_json("team_state.json", None)
    builder.add_json("evidence.json", [])
    builder.add_json("evidence_validation.json", {"errors": []})
    builder.add_json("evidence_acquisition.json", {})
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
                "scoring_rules_version": "fpl-2026-27-v1",
            }
        ],
    )
    builder.add_json(
        "run.json",
        {
            "schema_version": 1,
            "run_id": "freshness-attack",
            "code_sha": "abc",
            "config_sha": "cfg",
            "run_started_at": "2026-09-02T10:00:00Z",
            "acquired_at": "2026-09-02T10:05:00Z",
            "frozen_at": "2026-09-02T10:06:00Z",
            "target_gameweek": 3,
            "season": official.season,
            "entry_id": 63984,
            "max_horizon": 1,
            "scoring_rules_version": "fpl-2026-27-v1",
            "deadline": "2026-09-02T18:00:00Z",
            "evidence_required": False,
        },
    )
    builder.add_bytes(
        "config.yaml",
        b"""schema_version: 1
season: 2026-2027
entry_id: 63984
max_horizon: 1
scoring_rules_version: fpl-2026-27-v1
providers:
  - id: airsenal
    role: CHAMPION
    priority: 0
    serve_authorized: true
    predictive_status: INSUFFICIENT_HISTORY
    max_age_hours: 1
    requested_horizons: [1]
    path: acquisition/providers/airsenal.csv
""",
    )
    snapshot = builder.freeze(
        tmp_path / "snapshots",
        metadata={"frozen_at": "2026-09-02T10:06:00Z"},
    )

    stale_bundle = solve_snapshot(
        snapshot.root,
        tmp_path / "decision-stale.json",
        now=datetime(2026, 9, 2, 12, 30, tzinfo=timezone.utc),
    )

    assert stale_bundle.certification.actionable is False
    assert ReasonCode.CHAMPION_STALE in stale_bundle.certification.reasons

    # Production solve/replay omits ``now``. That path must be a pure function of the
    # sealed snapshot, not of when a runner happens to execute it. The sealed freeze
    # instant is one minute after the provider forecast and safely before the deadline.
    frozen_bundle = solve_snapshot(
        snapshot.root,
        tmp_path / "decision-frozen-clock.json",
    )

    assert frozen_bundle.certification.actionable is True
    assert ReasonCode.CHAMPION_STALE not in frozen_bundle.certification.reasons
