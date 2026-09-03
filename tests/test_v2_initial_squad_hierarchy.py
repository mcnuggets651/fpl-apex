from __future__ import annotations

from apex.runtime.solve import solve_snapshot
from test_v2_deterministic_replay import REPLAY_NOW, _freeze


EXPECTED_CANONICAL_SQUAD = (
    1,
    3,
    8,
    16,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    29,
    30,
    31,
)


def test_initial_squad_uses_explicit_hierarchical_objective_locks(tmp_path):
    snapshot = _freeze(tmp_path / "hierarchy-snapshots", "hierarchy", 1, None)
    bundle = solve_snapshot(snapshot.root, tmp_path / "hierarchy.json", now=REPLAY_NOW)

    assert bundle.system_decision is not None
    optimisation = bundle.provider_diagnostics["decision_optimisation"]
    assert optimisation["status"] == "OPTIMAL"
    solver = optimisation["solver"]

    # The primary FPL objective is submitted XI + captain xP only. The synthetic
    # fixture has eleven 10-point starters plus a 10-point captain copy.
    assert solver["primary_objective"] == 120.0
    assert solver["selected_approximate_objective"] == 120.0

    # Squad xP is a separate second-stage objective. Position/team constraints
    # allow exactly twelve 10-point players and three 3-point players: 129 xP.
    assert solver["secondary_squad_objective"] == 129.0
    assert solver["primary_tiebreak"] == (
        "HIERARCHICAL_PRIMARY_XP_THEN_SQUAD_XP_THEN_LEXICOGRAPHIC_SQUAD_BLOCKS"
    )
    assert solver["objective_lock_abs_tolerance"] == 1e-9

    # The final squad is the lexicographically canonical member of the exact
    # primary + exact squad-xP optimum set. This directly regresses the prior
    # 7e-9 lock escape that selected a different 128-xP squad across runners.
    assert bundle.system_decision.squad_ids == EXPECTED_CANONICAL_SQUAD
    assert sum(player_id > 15 for player_id in bundle.system_decision.squad_ids) == 12
    assert bundle.system_decision.objective == 120.0
