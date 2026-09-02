from __future__ import annotations

from collections import Counter
import math

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st

from apex_fpl.models.defcon import expected_defensive_contribution_points
from apex_fpl.models.ensemble import blend_projection
from apex_fpl.models.fixtures import fixture_multipliers
from apex_fpl.models.minutes import minutes_profile
from apex_fpl.models.projection import project_players
from apex_fpl.optimisation.mechanics import best_captain_vice_ids
from apex_fpl.optimisation.squad import optimise_squad


def _player(position: str = "DEF") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "player_id": 1,
                "first_name": "Red",
                "second_name": "Team",
                "web_name": "Red",
                "team": 1,
                "team_name": "A",
                "position": position,
                "price": 5.0,
                "expected_minutes": 90.0,
                "appearance_probability": 1.0,
                "minutes_60_plus_probability": 1.0,
                "expected_goals_per_90": 0.0,
                "expected_assists_per_90": 0.0,
                "defensive_contribution_per_90": 0.0,
                "saves_per_90": 0.0,
                "bps": 0.0,
                "minutes": 90.0,
                "penalties_order": 99,
                "corners_and_indirect_freekicks_order": 99,
                "direct_freekicks_order": 99,
            }
        ]
    )


def _fixture(expected_goals_against: float) -> pd.DataFrame:
    # Keep the fixture internally coherent with the Poisson clean-sheet model used
    # elsewhere in Apex, while exposing the same lambda required for the FPL
    # goals-conceded deduction.
    return pd.DataFrame(
        [
            {
                "team": 1,
                "gw": 1,
                "opponent": 2,
                "is_home": True,
                "attack_multiplier": 1.0,
                "defence_multiplier": 1.0,
                "clean_sheet_prob": math.exp(-expected_goals_against),
                "expected_goals_against": expected_goals_against,
            }
        ]
    )


def _expected_goals_conceded_deduction(lam: float) -> float:
    # If G~Poisson(lam), FPL deducts floor(G/2) points for GK/DEF.
    # E[floor(G/2)] = lam/2 - (1-exp(-2*lam))/4.
    return lam / 2.0 - (1.0 - math.exp(-2.0 * lam)) / 4.0


def test_defender_projection_exposes_negative_goals_conceded_component() -> None:
    out = project_players(_player("DEF"), _fixture(2.0), [1])
    assert "xp_goals_conceded" in out.columns
    assert float(out.loc[0, "xp_goals_conceded"]) == pytest.approx(
        -_expected_goals_conceded_deduction(2.0), abs=0.03
    )


def test_defender_xp_drop_includes_clean_sheet_and_goals_conceded_effects() -> None:
    easy = project_players(_player("DEF"), _fixture(0.5), [1]).iloc[0]
    hard = project_players(_player("DEF"), _fixture(3.0), [1]).iloc[0]
    actual_drop = float(easy["apex_xp"] - hard["apex_xp"])
    clean_sheet_drop = float(easy["xp_clean_sheet"] - hard["xp_clean_sheet"])
    required_gc_drop = _expected_goals_conceded_deduction(3.0) - _expected_goals_conceded_deduction(0.5)
    assert actual_drop >= clean_sheet_drop + required_gc_drop - 0.03


def test_fixture_model_already_provides_expected_goals_against() -> None:
    fixtures = pd.DataFrame([{"event": 1, "team_h": 1, "team_a": 2}])
    teams = pd.DataFrame(
        [
            {"id": 1, "strength": 1000},
            {"id": 2, "strength": 1000},
        ]
    )
    out = fixture_multipliers(fixtures, teams, [1], use_official_strength=False)
    assert out["expected_goals_against"].notna().all()
    assert (out["expected_goals_against"] > 0).all()


def test_full_gameweek_experts_are_allocated_once_across_double_gameweek_rows() -> None:
    base = pd.DataFrame(
        [
            {
                "player_id": 1,
                "gw": 1,
                "opponent": 2,
                "apex_xp": 3.0,
                "official_xp": 8.0,
                "airsenal_xp": 6.0,
                "apex_sd": 0.0,
                "apex_model_reliability": 1.0,
            },
            {
                "player_id": 1,
                "gw": 1,
                "opponent": 3,
                "apex_xp": 4.0,
                "official_xp": 8.0,
                "airsenal_xp": 6.0,
                "apex_sd": 0.0,
                "apex_model_reliability": 1.0,
            },
        ]
    )
    weights = {"official_ep": 0.25, "apex_model": 0.50, "airsenal": 0.25, "market": 0.0}
    out = blend_projection(base, weights, risk_penalty=0.0)
    assert out["expert_allocation_count"].tolist() == [2, 2]
    assert float(out["official_xp"].sum()) == pytest.approx(8.0)
    assert float(out["airsenal_xp"].sum()) == pytest.approx(6.0)
    expected_total = 0.50 * 7.0 + 0.25 * 8.0 + 0.25 * 6.0
    assert float(out["xp"].sum()) == pytest.approx(expected_total)


@given(
    minutes=st.floats(min_value=0, max_value=4000, allow_nan=False, allow_infinity=False),
    starts=st.floats(min_value=0, max_value=50, allow_nan=False, allow_infinity=False),
    pre_minutes=st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
    pre_starts=st.integers(min_value=0, max_value=12),
    pre_apps=st.integers(min_value=0, max_value=12),
    availability=st.integers(min_value=0, max_value=100),
)
@settings(max_examples=120, deadline=None)
def test_minutes_profile_probability_invariants(
    minutes: float,
    starts: float,
    pre_minutes: float,
    pre_starts: int,
    pre_apps: int,
    availability: int,
) -> None:
    if pre_starts > pre_apps:
        pre_starts = pre_apps
    frame = pd.DataFrame(
        [
            {
                "position": "MID",
                "minutes": minutes,
                "starts": starts,
                "starts_per_90": 0.5,
                "preseason_minutes": pre_minutes,
                "preseason_starts": pre_starts,
                "preseason_appearances": pre_apps,
                "chance_of_playing_next_round": availability,
                "status": "a",
            }
        ]
    )
    row = minutes_profile(frame).iloc[0]
    expected = float(row["expected_minutes"])
    start = float(row["start_probability"])
    appearance = float(row["appearance_probability"])
    p60 = float(row["minutes_60_plus_probability"])
    p80 = float(row["minutes_80_plus_probability"])
    assert 0.0 <= expected <= 90.0
    assert 0.0 <= start <= appearance <= 1.0
    assert 0.0 <= p80 <= p60 <= appearance <= 1.0
    assert all(np.isfinite(float(row[col])) for col in (
        "expected_minutes", "start_probability", "appearance_probability",
        "minutes_60_plus_probability", "minutes_80_plus_probability",
    ))


@given(
    a=st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    b=st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    c=st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    d=st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100, deadline=None)
def test_ensemble_mean_is_convex_when_all_experts_present(a: float, b: float, c: float, d: float) -> None:
    base = pd.DataFrame(
        [
            {
                "player_id": 1,
                "gw": 1,
                "official_xp": a,
                "apex_xp": b,
                "airsenal_xp": c,
                "market_xp": d,
                "apex_sd": 0.0,
                "minutes_confidence": 1.0,
                "role_confidence": 1.0,
                "apex_model_reliability": 1.0,
            }
        ]
    )
    out = blend_projection(
        base,
        {"official_ep": 0.25, "apex_model": 0.25, "airsenal": 0.25, "market": 0.25},
        risk_penalty=0.0,
    )
    value = float(out.loc[0, "xp"])
    assert min(a, b, c, d) - 1e-9 <= value <= max(a, b, c, d) + 1e-9
    assert np.isfinite(value)


@given(
    xp1=st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    xp2=st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    xp3=st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    p1=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    p2=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    p3=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=120, deadline=None)
def test_captain_vice_pair_matches_independent_enumeration(
    xp1: float, xp2: float, xp3: float, p1: float, p2: float, p3: float
) -> None:
    ids = [1, 2, 3]
    xp = {1: xp1, 2: xp2, 3: xp3}
    app = {1: p1, 2: p2, 3: p3}
    captain, vice, bonus = best_captain_vice_ids(ids, xp, app, captain_multiplier=2)

    def pair_bonus(capt: int, vice_id: int) -> float:
        # xP is unconditional, so the vice appearance probability is already inside
        # xp[vice_id]. Only captain no-show probability belongs here.
        return xp[capt] + (1.0 - app[capt]) * xp[vice_id]

    brute = max(pair_bonus(capt, vice_id) for capt in ids for vice_id in ids if capt != vice_id)
    assert captain != vice
    assert bonus == pytest.approx(brute)


@given(
    actions=st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False),
    share=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100, deadline=None)
def test_defcon_points_are_bounded(actions: float, share: float) -> None:
    out = expected_defensive_contribution_points(
        pd.Series(["DEF"]), pd.Series([actions]), pd.Series([share])
    )
    assert 0.0 <= float(out[0]) <= 2.0


def _randomised_pool(seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    pid = 1
    for position, count in (("GK", 4), ("DEF", 12), ("MID", 12), ("FWD", 8)):
        for _ in range(count):
            rows.append(
                {
                    "player_id": pid,
                    "web_name": f"P{pid}",
                    "team": 1 + ((pid - 1) % 12),
                    "team_name": f"T{1 + ((pid - 1) % 12)}",
                    "position": position,
                    "price": float(rng.uniform(4.0, 8.0)),
                    "gw1_xp": float(rng.uniform(1.0, 9.0)),
                    "horizon_xp": float(rng.uniform(4.0, 40.0)),
                    "appearance_probability": float(rng.uniform(0.5, 1.0)),
                }
            )
            pid += 1
    return pd.DataFrame(rows)


@pytest.mark.parametrize("seed", list(range(12)))
def test_squad_solver_output_always_respects_fpl_legality(seed: int) -> None:
    pool = _randomised_pool(seed)
    result = optimise_squad(pool, budget=120.0, max_per_team=3)
    assert result.status == "Optimal"
    squad = result.squad
    xi = result.xi
    assert len(squad) == 15 and squad["player_id"].nunique() == 15
    assert len(xi) == 11 and xi["player_id"].nunique() == 11
    assert set(xi["player_id"]).issubset(set(squad["player_id"]))
    assert float(squad["price"].sum()) <= 120.0 + 1e-8
    assert max(Counter(squad["team_name"]).values()) <= 3
    assert Counter(squad["position"]) == Counter({"GK": 2, "DEF": 5, "MID": 5, "FWD": 3})
    counts = Counter(xi["position"])
    assert counts["GK"] == 1
    assert 3 <= counts["DEF"] <= 5
    assert 2 <= counts["MID"] <= 5
    assert 1 <= counts["FWD"] <= 3
