from __future__ import annotations

from datetime import datetime, timedelta, timezone
from tempfile import TemporaryDirectory
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from apex.decision.mechanics import best_fixed_squad_mechanics
from apex.decision.transfers import optimise_transfer_horizon
from apex.domain.models import (
    CoverageStatus,
    EvidenceEffect,
    EvidenceRecord,
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    ProductionProjectionSurface,
    ProjectionRow,
    TeamState,
)
from apex.domain.rules import validate_xi
from apex.forecast.contract import validate_projection_surface
from apex.governance.evidence import validate_evidence
from apex.runtime.attempts import audit_release_tags
from apex.runtime.snapshot import SnapshotBuilder

SEASON = "2026-2027"
NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


def _players(*, include_alternative_mid: bool = False) -> tuple[OfficialPlayer, ...]:
    rows = [
        OfficialPlayer(1, "GK1", 1, Position.GK, 45, "a", True, 1001),
        OfficialPlayer(2, "GK2", 2, Position.GK, 45, "a", True, 1002),
        OfficialPlayer(3, "D3", 1, Position.DEF, 45, "a", True, 1003),
        OfficialPlayer(4, "D4", 2, Position.DEF, 45, "a", True, 1004),
        OfficialPlayer(5, "D5", 3, Position.DEF, 45, "a", True, 1005),
        OfficialPlayer(6, "D6", 4, Position.DEF, 45, "a", True, 1006),
        OfficialPlayer(7, "D7", 5, Position.DEF, 45, "a", True, 1007),
        OfficialPlayer(8, "M8", 3, Position.MID, 45, "a", True, 1008),
        OfficialPlayer(9, "M9", 4, Position.MID, 45, "a", True, 1009),
        OfficialPlayer(10, "M10", 5, Position.MID, 45, "a", True, 1010),
        OfficialPlayer(11, "M11", 6, Position.MID, 45, "a", True, 1011),
        OfficialPlayer(12, "A", 7, Position.MID, 100, "a", True, 1012),
        OfficialPlayer(13, "F13", 6, Position.FWD, 45, "a", True, 1013),
        OfficialPlayer(14, "F14", 7, Position.FWD, 45, "a", True, 1014),
        OfficialPlayer(15, "F15", 8, Position.FWD, 45, "a", True, 1015),
    ]
    if include_alternative_mid:
        rows.append(OfficialPlayer(16, "B", 8, Position.MID, 90, "a", True, 1016))
    return tuple(rows)


def _official(*, include_alternative_mid: bool = False) -> OfficialSnapshot:
    return OfficialSnapshot(
        1,
        SEASON,
        NOW.isoformat(),
        "a" * 64,
        _players(include_alternative_mid=include_alternative_mid),
        (),
        {
            1: "2026-08-15T10:00:00Z",
            2: "2026-08-22T10:00:00Z",
            3: "2026-09-04T17:30:00Z",
            4: "2026-09-12T10:00:00Z",
            5: "2026-09-19T10:00:00Z",
        },
    )


def _surface(
    xp_by_horizon: dict[int, dict[int, float]],
    *,
    appearance: dict[int, float] | None = None,
) -> ProductionProjectionSurface:
    rows = []
    for horizon, values in sorted(xp_by_horizon.items()):
        gameweek = 2 + horizon
        for player_id, xp in sorted(values.items()):
            rows.append(
                ProjectionRow(
                    player_id,
                    gameweek,
                    horizon,
                    float(xp),
                    p_appearance=(
                        float(appearance[player_id])
                        if appearance is not None
                        else None
                    ),
                    coverage_status=CoverageStatus.FORECAST,
                )
            )
    horizons = tuple(sorted(xp_by_horizon))
    return ProductionProjectionSurface(
        1,
        "airsenal",
        "adversarial-test",
        NOW.isoformat(),
        SEASON,
        "a" * 64,
        "2026-27",
        horizons,
        tuple(rows),
    )


def _team() -> TeamState:
    squad = tuple(range(1, 16))
    sell = {player_id: 45 for player_id in squad}
    sell[12] = 90
    purchase = {player_id: 45 for player_id in squad}
    purchase[12] = 80
    return TeamState(
        1,
        63984,
        2,
        squad,
        10,
        5,
        purchase,
        sell,
        None,
        True,
    )


@settings(max_examples=80, deadline=None)
@given(
    xp=st.lists(
        st.floats(min_value=0.0, max_value=25.0, allow_nan=False, allow_infinity=False),
        min_size=15,
        max_size=15,
    ),
    appearance=st.lists(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=15,
        max_size=15,
    ),
)
def test_random_exact_mechanics_always_returns_a_legal_partition(xp, appearance):
    official = _official()
    ids = tuple(range(1, 16))
    surface = _surface(
        {1: {player_id: xp[player_id - 1] for player_id in ids}},
        appearance={player_id: appearance[player_id - 1] for player_id in ids},
    )
    result = best_fixed_squad_mechanics(official, surface, ids, horizon=1)
    assert len(result.xi_ids) == 11
    assert len(set(result.xi_ids)) == 11
    assert result.captain_id in result.xi_ids
    assert result.vice_captain_id in result.xi_ids
    assert result.captain_id != result.vice_captain_id
    assert set(result.xi_ids).isdisjoint(result.bench_order)
    assert set(result.xi_ids) | set(result.bench_order) == set(ids)
    assert not validate_xi(official.player_map(), ids, result.xi_ids)


@settings(max_examples=60, deadline=None)
@given(value=st.sampled_from([float("nan"), float("inf"), float("-inf")]))
def test_nonfinite_forecasts_fail_contract_validation(value):
    official = _official()
    ids = tuple(range(1, 16))
    surface = _surface({1: {player_id: 3.0 for player_id in ids}})
    rows = list(surface.rows)
    row = rows[0]
    rows[0] = ProjectionRow(
        row.element_id,
        row.gameweek,
        row.horizon,
        value,
        coverage_status=CoverageStatus.FORECAST,
    )
    poisoned = ProductionProjectionSurface(
        surface.schema_version,
        surface.provider_id,
        surface.provider_version,
        surface.generated_at,
        surface.season,
        surface.source_snapshot,
        surface.scoring_rules_version,
        surface.supported_horizons,
        tuple(rows),
    )
    assert validate_projection_surface(poisoned, official)


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED AVD-001: draft final release poisons frozen tag-only attempt audit",
)
def test_attempt_audit_must_not_count_draft_final_as_completed_final():
    key = "2026-2027/999-1"
    audit = audit_release_tags(
        [
            {
                "tag_name": f"apex-v2/intent/{key}",
                "draft": False,
                "immutable": True,
                "created_at": (NOW - timedelta(hours=5)).isoformat(),
            },
            {
                "tag_name": f"apex-v2/final/{key}",
                "draft": True,
                "immutable": False,
                "created_at": (NOW - timedelta(hours=4)).isoformat(),
            },
        ],
        now=NOW,
    )
    assert f"apex-v2/intent/{key}" in audit.missing_finals
    assert f"apex-v2/final/{key}" not in audit.finals


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED AVD-002: signed negative xP is accepted but exact mechanics clamps it to zero",
)
def test_exact_mechanics_must_preserve_signed_expected_point_ranking():
    official = _official()
    ids = tuple(range(1, 16))
    values = {player_id: 20.0 for player_id in ids}
    values.update({3: -100.0, 4: -90.0, 5: -80.0, 6: -2.0, 7: -1.0})
    surface = _surface(
        {1: values},
        appearance={player_id: 1.0 for player_id in ids},
    )
    assert not validate_projection_surface(surface, official)
    result = best_fixed_squad_mechanics(official, surface, ids, horizon=1)
    selected_defenders = {
        player_id
        for player_id in result.xi_ids
        if official.player_map()[player_id].position == Position.DEF
    }
    # With signed max-EV and the mandatory three-defender floor, the least-negative
    # defenders must be selected. The frozen exact path currently zero-clamps all
    # five and therefore tie-breaks toward worse IDs.
    assert selected_defenders == {5, 6, 7}


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED AVD-003: future-dated evidence is not rejected prospectively",
)
def test_evidence_must_not_be_actionable_before_its_published_at():
    official = _official()
    record = EvidenceRecord(
        "future-evidence",
        12,
        "Official club",
        "https://example.com/club/item",
        "official_club",
        (NOW + timedelta(hours=1)).isoformat(),
        NOW.isoformat(),
        (NOW + timedelta(hours=2)).isoformat(),
        "explicit_absence",
        3,
        EvidenceEffect.HARD_EXCLUDE,
        "0" * 64,
        "A ruled out",
    )
    errors = validate_evidence((record,), official, now=NOW)
    assert errors


def _roundtrip_result():
    official = _official(include_alternative_mid=True)
    ids = tuple(range(1, 17))
    values = {}
    for horizon in (1, 2, 3):
        values[horizon] = {player_id: 10.0 for player_id in ids}
        for player_id in (8, 9, 10, 11):
            values[horizon][player_id] = 60.0
    values[1][12], values[1][16] = 0.0, 100.0
    values[2][12], values[2][16] = 100.0, 0.0
    values[3][12], values[3][16] = 0.0, 100.0
    return optimise_transfer_horizon(
        official,
        _surface(values),
        _team(),
        max_horizon=3,
        candidate_limit=1,
        candidate_regret_fraction=0.0,
    )


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED AVD-004: transfer weeks are labelled from min season deadline, not live target GW",
)
def test_transfer_horizon_week_labels_must_start_after_published_gameweek():
    result = _roundtrip_result()
    assert result.status == "OPTIMAL"
    assert [week.gameweek for week in result.weeks] == [3, 4, 5]


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED AVD-005: sell-rebuy-sell reuses original selling basis after reacquisition",
)
def test_reacquired_player_must_reset_future_selling_basis():
    result = _roundtrip_result()
    assert result.status == "OPTIMAL"
    assert [week.transfers_out for week in result.weeks] == [(12,), (16,), (12,)]
    assert [week.transfers_in for week in result.weeks] == [(16,), (12,), (16,)]
    # Initial bank 1.0m: A original sale 9.0 -> B buy 9.0 => 1.0m;
    # B sale 9.0 -> A REBUY 10.0 => 0.0m; A was then bought at 10.0 and,
    # with static future prices, should sell for 10.0 -> B 9.0 => 1.0m.
    assert result.weeks[-1].bank_tenths == 10


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED AVD-006 dormant API defect: SnapshotBuilder accepts traversal names",
)
def test_snapshot_builder_must_reject_parent_or_absolute_member_names():
    builder = SnapshotBuilder()
    with pytest.raises(ValueError):
        builder.add_bytes("../escape.json", b"{}")
    with pytest.raises(ValueError):
        builder.add_bytes("/absolute.json", b"{}")


def test_snapshot_builder_tamper_is_detected_for_valid_member_name():
    with TemporaryDirectory() as temp:
        builder = SnapshotBuilder()
        builder.add_bytes("safe/file.bin", b"original")
        snapshot = builder.freeze(Path(temp) / "snapshots")
        (snapshot.root / "safe/file.bin").write_bytes(b"tampered")
        with pytest.raises(RuntimeError, match="integrity violation"):
            snapshot.read_bytes("safe/file.bin")
