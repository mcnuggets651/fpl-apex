from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from apex_fpl.optimisation.transfers import TransferPlan
from apex_fpl.services.release_profile import INSEASON_SELECTOR


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_inseason_action_sensitivity.py"
SPEC = spec_from_file_location("audit_inseason_action_sensitivity", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _week(transfers: int = 5):
    squad = [{"player_id": pid} for pid in range(1, 16)]
    return {
        "gw": 2,
        "transfers": transfers,
        "hit_cost": max(0, transfers - 1) * 4,
        "transfers_in": [{"player_id": pid} for pid in range(11, 11 + transfers)],
        "transfers_out": [{"player_id": pid} for pid in range(1, 1 + transfers)],
        "squad": squad,
    }


def _plan(objective: float, transfers: int = 5):
    return TransferPlan(
        "Optimal",
        objective,
        [_week(transfers)],
        solver_status_code=0,
        solver_message="optimal",
        objective_upper_bound=objective,
        mip_gap=0.0,
    )


def _bundle():
    state = SimpleNamespace(
        squad=set(range(1, 16)),
        bank=0.0,
        free_transfers=1,
        selling_prices={pid: 5.0 for pid in range(1, 16)},
        selling_prices_exact=True,
        source="public_fpl_entry",
        published_gw=1,
        public_deadline_snapshot=True,
    )
    players = pd.DataFrame({
        "player_id": list(range(1, 21)),
        "web_name": [f"P{i}" for i in range(1, 21)],
        "position": ["MID"] * 20,
    })
    projections = pd.DataFrame({
        "player_id": list(range(1, 21)),
        "gw": [2] * 20,
        "xp": [4.0] * 20,
    })
    out = SimpleNamespace(
        team_state=SimpleNamespace(ok=True, state=state),
        players=players,
        news_audit=pd.DataFrame(),
        projections=projections,
        gameweeks=[2, 3],
    )
    return SimpleNamespace(
        bundle_id="bundle",
        settings={"max_per_team": 3, "fixture_decay": 0.92},
        to_pipeline_output=lambda: out,
    )


def _canonical():
    return {
        "decision_bundle_id": "bundle",
        "recommendation": {
            "selector": INSEASON_SELECTOR,
            "objective": 100.0,
            "action_now": _week(5),
        },
    }


def test_inseason_sensitivity_proves_aggressive_hit_against_same_surface_counterfactuals(monkeypatch):
    plans = iter([
        _plan(100.0, 5),  # fresh unconstrained replay
        _plan(90.0, 0),   # roll
        _plan(92.0, 1),   # no hit
        _plan(100.0, 5),  # same transfer count
        _plan(98.0, 4),   # one fewer
        _plan(99.0, 6),   # one more
    ])
    monkeypatch.setattr(MODULE, "optimise_transfer_plan_view", lambda **kwargs: next(plans))
    monkeypatch.setattr(MODULE, "evidence_eligibility", lambda players, news: (players, {}))
    monkeypatch.setattr(MODULE, "captain_eligible_ids", lambda players: set(players.player_id))

    audit = MODULE.audit_inseason_action_sensitivity(bundle=_bundle(), canonical=_canonical())

    assert audit["ready"] is True
    assert audit["published_action"]["transfers"] == 5
    assert {row["name"] for row in audit["counterfactuals"]} == {
        "roll",
        "no_hit",
        "published_transfer_count",
        "one_fewer_transfer",
        "one_more_transfer",
    }
    no_hit = next(row for row in audit["counterfactuals"] if row["name"] == "no_hit")
    assert no_hit["regret_vs_unconstrained"] == 8.0
    assert any("aggressive hit action certified" in row for row in audit["warnings"])
    assert any("public deadline snapshot" in row for row in audit["warnings"])


def test_inseason_sensitivity_fails_closed_on_inconclusive_counterfactual(monkeypatch):
    limit = TransferPlan(
        "SolverLimit",
        95.0,
        [],
        solver_status_code=1,
        solver_message="time limit",
        objective_upper_bound=101.0,
        mip_gap=0.05,
    )
    plans = iter([_plan(100.0, 5), limit, _plan(92.0, 1), _plan(100.0, 5), _plan(98.0, 4), _plan(99.0, 6)])
    monkeypatch.setattr(MODULE, "optimise_transfer_plan_view", lambda **kwargs: next(plans))
    monkeypatch.setattr(MODULE, "evidence_eligibility", lambda players, news: (players, {}))
    monkeypatch.setattr(MODULE, "captain_eligible_ids", lambda players: set(players.player_id))

    audit = MODULE.audit_inseason_action_sensitivity(bundle=_bundle(), canonical=_canonical())

    assert audit["ready"] is False
    assert any("roll counterfactual is inconclusive" in row for row in audit["blockers"])
