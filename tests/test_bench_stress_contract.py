from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

import pandas as pd


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_bench_stress.py"
SPEC = spec_from_file_location("audit_bench_stress", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_bench_stress_uses_exact_canonical_submission_for_inseason_selector():
    positions = ["GK", "GK"] + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3
    players = pd.DataFrame({
        "player_id": list(range(1, 16)),
        "web_name": [f"P{i}" for i in range(1, 16)],
        "position": positions,
        "appearance_probability": [0.9] * 15,
    })
    projections = pd.DataFrame({
        "player_id": list(range(1, 16)),
        "gw": [2] * 15,
        "xp": [float(16 - i) for i in range(1, 16)],
    })
    out = SimpleNamespace(players=players, projections=projections, gameweeks=[2, 3])
    bundle = SimpleNamespace(bundle_id="bundle", to_pipeline_output=lambda: out)

    squad = [{"player_id": pid} for pid in range(1, 16)]
    xi_ids = [1, 3, 4, 5, 8, 9, 10, 11, 12, 13, 14]
    canonical = {
        "decision_bundle_id": "bundle",
        "recommendation": {
            "selector": "receding_horizon_current_team_maximum_ev",
            "current_gameweek": 2,
            "squad": squad,
            "xi": [{"player_id": pid} for pid in xi_ids],
            "captain_id": 8,
            "vice_captain_id": 9,
            "bench_gk_id": 2,
            "outfield_bench_order_ids": [6, 7, 15],
        },
    }

    payload, frame = MODULE.audit_canonical_bench_stress(bundle=bundle, canonical=canonical)

    assert payload["contract"] == "apex-bench-stress-v2"
    assert payload["selector"] == "receding_horizon_current_team_maximum_ev"
    assert payload["submitted_xi_ids"] == xi_ids
    assert payload["submitted_outfield_bench_order_ids"] == [6, 7, 15]
    assert payload["fixed_submission"] is True
    assert payload["bench_reordered_with_hindsight"] is False
    assert set(frame["absence_count"]) == {1, 2}
