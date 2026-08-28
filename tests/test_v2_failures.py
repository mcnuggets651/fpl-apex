from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from apex.domain.models import (
    CoverageStatus,
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    ProjectionRow,
    ProjectionSurface,
    ProviderHealth,
    ProviderRole,
    ProviderStatus,
    Qualification,
)
from apex.domain.rules import calculate_selling_price, validate_squad
from apex.forecast.contract import coverage_errors
from apex.forecast.qualification import qualify_surface
from apex.forecast.registry import NoServingProvider, serving_provider
from apex.runtime.attempts import audit_release_tags
from apex.runtime.snapshot import SnapshotBuilder, open_frozen_snapshot


def official():
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
        "2026-08-28T10:00:00+00:00",
        "snap",
        tuple(players),
        (),
        {2: "2026-08-29T10:00:00Z"},
    )


def surface(
    official_snapshot,
    *,
    generated="2026-08-28T10:00:00+00:00",
    missing=(),
    provider="p",
):
    missing = set(missing)
    rows = tuple(
        ProjectionRow(
            player.element_id,
            2,
            1,
            None if player.element_id in missing else 3.0,
            coverage_status=(
                CoverageStatus.NO_FORECAST
                if player.element_id in missing
                else CoverageStatus.FORECAST
            ),
            coverage_reason=(
                "missing" if player.element_id in missing else None
            ),
        )
        for player in official_snapshot.players
    )
    return ProjectionSurface(
        1,
        provider,
        "v1",
        generated,
        official_snapshot.season,
        official_snapshot.source_hash,
        "2026-2027",
        (1,),
        (),
        rows,
    )


def test_no_forecast_never_counts_as_coverage():
    official_snapshot = official()
    projection = surface(official_snapshot, missing={1})
    assert coverage_errors(
        projection,
        official_snapshot.decision_universe(),
        horizon=1,
    )


def test_shadow_never_serves_even_when_authorized():
    official_snapshot = official()
    projection = surface(official_snapshot)
    provider = ProviderStatus(
        "p",
        ProviderRole.SHADOW,
        0,
        ProviderHealth.HEALTHY,
        {1: Qualification.QUALIFIED},
        projection,
        (),
        True,
    )
    with pytest.raises(NoServingProvider):
        serving_provider(
            [provider],
            horizon=1,
            decision_universe=official_snapshot.decision_universe(),
        )


def test_unauthorized_standby_cannot_silently_serve():
    official_snapshot = official()
    projection = surface(official_snapshot)
    provider = ProviderStatus(
        "p",
        ProviderRole.STANDBY,
        0,
        ProviderHealth.HEALTHY,
        {1: Qualification.QUALIFIED},
        projection,
        (),
        False,
    )
    with pytest.raises(NoServingProvider):
        serving_provider(
            [provider],
            horizon=1,
            decision_universe=official_snapshot.decision_universe(),
        )


def test_stale_surface_unqualified():
    official_snapshot = official()
    projection = surface(
        official_snapshot,
        generated="2026-08-20T00:00:00Z",
    )
    qualification = qualify_surface(
        projection,
        official_snapshot,
        decision_universe=official_snapshot.decision_universe(),
        requested_horizons=(1,),
        max_age_hours=18,
        now=datetime(2026, 8, 28, 12, tzinfo=timezone.utc),
    )
    assert qualification.operational == Qualification.UNQUALIFIED
    assert qualification.health == ProviderHealth.STALE


def test_snapshot_detects_post_freeze_mutation(tmp_path: Path):
    builder = SnapshotBuilder()
    builder.add_json("x.json", {"a": 1})
    snapshot = builder.freeze(tmp_path)
    (snapshot.root / "x.json").write_text('{"a":2}')
    with pytest.raises(RuntimeError):
        open_frozen_snapshot(snapshot.root)


def test_snapshot_rejects_new_input_after_freeze(tmp_path: Path):
    builder = SnapshotBuilder()
    builder.add_json("x.json", {"a": 1})
    builder.freeze(tmp_path)
    with pytest.raises(RuntimeError):
        builder.add_json("y.json", {})


def test_orphaned_intent_detected_after_grace():
    now = datetime(2026, 8, 28, 12, tzinfo=timezone.utc)
    releases = [
        {
            "tag_name": "apex-v2/intent/2026-2027/run1",
            "created_at": (now - timedelta(hours=5)).isoformat(),
        },
        {
            "tag_name": "apex-v2/intent/2026-2027/run2",
            "created_at": now.isoformat(),
        },
        {
            "tag_name": "apex-v2/final/2026-2027/run3",
            "created_at": now.isoformat(),
        },
    ]
    audit = audit_release_tags(releases, now=now)
    assert audit.missing_finals == (
        "apex-v2/intent/2026-2027/run1",
    )
    assert audit.in_progress == (
        "apex-v2/intent/2026-2027/run2",
    )


def test_fpl_selling_price_rounds_down_half_profit():
    assert calculate_selling_price(50, 55) == 52
    assert calculate_selling_price(50, 56) == 53
    assert calculate_selling_price(50, 47) == 47


def test_existing_team_value_over_100m_can_still_be_structurally_legal():
    official_snapshot = official()
    by_team_position = {
        (player.team_id, player.position): []
        for player in official_snapshot.players
    }
    for player in official_snapshot.players:
        by_team_position[
            player.team_id,
            player.position,
        ].append(player.element_id)
    ids = (
        [
            by_team_position[1, Position.GK][0],
            by_team_position[2, Position.GK][0],
        ]
        + [
            by_team_position[team_id, Position.DEF][0]
            for team_id in range(1, 6)
        ]
        + [
            by_team_position[team_id, Position.MID][0]
            for team_id in range(1, 6)
        ]
        + [
            by_team_position[team_id, Position.FWD][0]
            for team_id in range(3, 6)
        ]
    )
    players = {
        player_id: OfficialPlayer(
            player.element_id,
            player.web_name,
            player.team_id,
            player.position,
            80,
            player.status,
            player.can_transact,
        )
        for player_id, player in official_snapshot.player_map().items()
    }
    assert validate_squad(players, ids, budget_tenths=None) == ()
    assert validate_squad(players, ids, budget_tenths=1000)
