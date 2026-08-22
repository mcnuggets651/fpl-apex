from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "apply_joint_path_promotion.py"
SPEC = spec_from_file_location("apply_joint_path_promotion", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _result(*, status="optimal", stable=True, within=True):
    return SimpleNamespace(
        status=status,
        candidate_pool_stable=stable,
        selected=SimpleNamespace(within_gw1_band=within),
    )


def _weekly_strategy():
    squad = [
        {
            "player_id": player_id,
            "web_name": f"P{player_id}",
            "team_name": "Club",
            "position": "GK" if player_id in {1, 12} else "MID",
            "price": 5.0,
        }
        for player_id in range(1, 16)
    ]
    return {
        "status": "optimal",
        "state_transition_reconciled": True,
        "canonical_squad": squad,
        "canonical_xi": squad[:11],
        "canonical_captain": "P1",
        "canonical_captain_id": 1,
        "canonical_vice_captain": "P2",
        "canonical_vice_captain_id": 2,
        "canonical_bench_gk": "P12",
        "canonical_bench_gk_id": 12,
        "canonical_outfield_bench_order": ["P13", "P14", "P15"],
        "canonical_outfield_bench_order_ids": [13, 14, 15],
        "canonical_expected_points": 50.0,
        "optimal_objective": 100.0,
        "next_gw": 2,
        "recommended_action": "roll",
        "recommended_transfers": 0,
        "recommended_hit": 0,
        "roll_regret": 0.0,
        "action_now": {"gw": 2, "squad": squad},
        "contingent_future": [],
    }


def test_launch_gate_requires_gw1_floor() -> None:
    gate = MODULE._launch_gate(_result(within=False))
    assert gate["gw1_first_optimal"] is True
    assert gate["candidate_pool_stable"] is True
    assert gate["gw1_floor_respected"] is False
    assert gate["promotion_candidate"] is False


def test_launch_gate_requires_candidate_stability() -> None:
    gate = MODULE._launch_gate(_result(stable=False))
    assert gate["gw1_floor_respected"] is True
    assert gate["candidate_pool_stable"] is False
    assert gate["promotion_candidate"] is False


def test_launch_gate_has_no_material_eight_week_gain_requirement() -> None:
    gate = MODULE._launch_gate(_result())
    assert gate == {
        "gw1_first_optimal": True,
        "candidate_pool_stable": True,
        "gw1_floor_respected": True,
        "promotion_candidate": True,
    }


def test_launch_gate_requires_optimal_gw1_solve() -> None:
    gate = MODULE._launch_gate(_result(status="infeasible"))
    assert gate["gw1_first_optimal"] is False
    assert gate["promotion_candidate"] is False


def test_weekly_strategy_publishes_exact_bench_names_and_ids() -> None:
    strategy = _weekly_strategy()
    payload = {}

    MODULE._apply_weekly_strategy(payload, {"weekly_strategy": strategy})

    recommendation = payload["recommendation"]
    assert recommendation["bench_gk"] == "P12"
    assert recommendation["bench_gk_id"] == 12
    assert recommendation["outfield_bench_order"] == ["P13", "P14", "P15"]
    assert recommendation["outfield_bench_order_ids"] == [13, 14, 15]
    squad_ids = {int(row["player_id"]) for row in recommendation["squad"]}
    xi_ids = {int(row["player_id"]) for row in recommendation["xi"]}
    assert {
        recommendation["bench_gk_id"],
        *recommendation["outfield_bench_order_ids"],
    } == squad_ids - xi_ids


def test_weekly_strategy_fails_closed_on_bench_name_id_drift() -> None:
    strategy = _weekly_strategy()
    strategy["canonical_outfield_bench_order_ids"] = [14, 13, 15]

    with pytest.raises(SystemExit, match="name/id identity does not reconcile"):
        MODULE._apply_weekly_strategy({}, {"weekly_strategy": strategy})


def test_weekly_strategy_fails_closed_when_bench_is_not_xi_complement() -> None:
    strategy = _weekly_strategy()
    strategy["canonical_xi"] = strategy["canonical_squad"][:10] + [
        strategy["canonical_squad"][12]
    ]

    with pytest.raises(SystemExit, match="exact complement of the XI"):
        MODULE._apply_weekly_strategy({}, {"weekly_strategy": strategy})
