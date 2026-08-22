from __future__ import annotations

import pandas as pd
import pytest

from apex_fpl.config import load_settings
from apex_fpl.optimisation import exact_decision as exact_decision_module
from apex_fpl.optimisation.exact_decision import optimise_exact_horizon_decision


def _players() -> pd.DataFrame:
    positions = ["GK"] * 2 + ["DEF"] * 6 + ["MID"] * 5 + ["FWD"] * 3
    return pd.DataFrame(
        [
            {
                "player_id": pid,
                "web_name": f"P{pid}",
                "team": pid,
                "team_name": f"T{pid}",
                "position": position,
                "price": 4.5,
                "appearance_probability": 0.82 + (pid % 4) * 0.04,
                "expected_minutes": 75.0,
                "start_probability": 0.8,
                "projection_confidence": 0.7,
                "horizon_xp": 20.0,
            }
            for pid, position in enumerate(positions, start=1)
        ]
    )


def _projections() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "player_id": pid,
                "gw": gw,
                "xp": 2.0 + pid / 10.0 + gw / 20.0,
            }
            for gw in (1, 2)
            for pid in range(1, 17)
        ]
    )


def test_exact_horizon_decision_reconciles_and_is_deterministic() -> None:
    kwargs = dict(
        players=_players(),
        projections=_projections(),
        gameweeks=[1],
        decay=0.9,
        candidate_limit=2,
        candidate_regret_fraction=0.05,
        captain_eligible=set(range(1, 17)),
    )
    first = optimise_exact_horizon_decision(**kwargs)
    assert first.status == "Optimal"
    assert len(first.solution.squad) == 15
    assert len(first.solution.xi) == 11
    assert len(first.candidates) == 2
    assert len({candidate.squad_ids for candidate in first.candidates}) == 2
    # Reaching the resource ceiling is never evidence that the governed objective
    # band was exhausted. The secondary selector must fall back to generation rank
    # one, which is the globally optimal canonical maximum-EV MILP result.
    assert first.shortlist_complete is False
    rank_one = next(
        candidate for candidate in first.candidates if candidate.generation_rank == 1
    )
    assert tuple(sorted(first.solution.squad.player_id.astype(int))) == rank_one.squad_ids
    assert first.solution.objective == pytest.approx(
        sum(
            week.discount * week.mechanics.expected_total_points
            for week in first.weeks
        )
    )
    assert set(first.solution.captain["player_id"]) == {
        first.weeks[0].mechanics.captain_id
    }
    assert set(first.solution.vice_captain["player_id"]) == {
        first.weeks[0].mechanics.vice_captain_id
    }
    assert first.solution.solver["selection_contract"] == (
        "global_max_ev_then_bounded_exact_secondary"
    )
    assert first.solution.solver["selector_mode"] == "maximum_ev_fallback"
    assert first.solution.solver["global_max_ev_certified"] is True
    assert first.solution.solver["secondary_exact_selector_certified"] is False
    assert first.solution.solver["authoritative_objective"] == (
        "global_max_ev_with_exact_horizon_mechanics"
    )


def test_subsequent_shortlist_solves_receive_governed_floor(monkeypatch) -> None:
    calls: list[float | None] = []
    original = exact_decision_module.optimise_initial_horizon

    def wrapped(*args, **kwargs):
        calls.append(kwargs.get("min_reference_objective"))
        return original(*args, **kwargs)

    monkeypatch.setattr(exact_decision_module, "optimise_initial_horizon", wrapped)
    optimise_exact_horizon_decision(
        _players(),
        _projections(),
        [1],
        candidate_limit=2,
        candidate_regret_fraction=0.05,
        captain_eligible=set(range(1, 17)),
    )
    assert calls[0] is None
    assert calls[1] is not None


def test_production_exact_secondary_budget_is_bounded() -> None:
    settings = load_settings("config/apex.yaml")
    # This is a secondary audit resource budget, not a global-optimality proof.
    # If the 0.5% band is denser than this, production uses the certified rank-one
    # maximum-EV fallback rather than pretending the band was exhausted.
    assert settings.exact_candidate_limit == 16
    assert settings.exact_candidate_regret_fraction == pytest.approx(0.005)


def test_exact_horizon_rejects_invalid_candidate_controls() -> None:
    with pytest.raises(ValueError, match="candidate_limit"):
        optimise_exact_horizon_decision(
            _players(), _projections(), [1], candidate_limit=0
        )
    with pytest.raises(ValueError, match="between 0 and 5%"):
        optimise_exact_horizon_decision(
            _players(), _projections(), [1], candidate_regret_fraction=0.06
        )


def test_exact_rescore_honours_pre_solve_xi_eligibility() -> None:
    players = _players()
    decision = optimise_exact_horizon_decision(
        players,
        _projections(),
        [1],
        candidate_limit=1,
        captain_eligible=set(players.player_id) - {16},
        xi_eligible=set(players.player_id) - {16},
        locked={16},
    )
    assert decision.status == "Optimal"
    assert 16 in set(decision.solution.squad.player_id)
    assert 16 not in set(decision.solution.xi.player_id)
