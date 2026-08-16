from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys


def _rows() -> list[dict]:
    rows = []
    positions = [
        "GK",
        "GK",
        "DEF",
        "DEF",
        "DEF",
        "DEF",
        "DEF",
        "MID",
        "MID",
        "MID",
        "MID",
        "MID",
        "FWD",
        "FWD",
        "FWD",
    ]
    for idx, position in enumerate(positions, start=1):
        rows.append(
            {
                "player_id": idx,
                "web_name": f"P{idx}",
                "team_name": f"T{(idx % 5) + 1}",
                "position": position,
                "price": 5.0,
                "gw1_xp": 3.0 + idx / 10.0,
                "horizon_xp": 20.0 + idx / 10.0,
                "expected_minutes": 75.0,
                "start_probability": 0.8,
                "projection_confidence": 0.7,
                "tactical_role": "test role",
                "tactical_role_source": "statistical_inference",
            }
        )
    return rows


def _solution(name: str, objective: float) -> dict:
    squad = _rows()
    xi = squad[:1] + squad[2:8] + squad[8:12]
    assert len(xi) == 11
    return {
        "status": "Optimal",
        "objective": objective,
        "squad": squad,
        "xi": xi,
        "captain": [{"web_name": name}],
        "vice_captain": [{"web_name": "Vice"}],
        "bench": [],
    }


def _mechanics(captain: str) -> dict:
    return {
        "captain_id": 1,
        "vice_captain_id": 2,
        "captain_name": captain,
        "vice_captain_name": "Vice",
        "bench_gk_name": "P2",
        "outfield_bench_order_names": ["P13", "P14", "P15"],
        "expected_total_points": 55.5,
    }


def _pinnacle(bootstrap: str = "boot", fixtures: str = "fix") -> dict:
    now = datetime.now(timezone.utc).isoformat()
    exact_solution = _solution("ExactCap", 102.0)
    return {
        "contract": "pinnacle-test",
        "generated_at": now,
        "safe_to_act": True,
        "full_apex_ready": True,
        "pinnacle_ready": True,
        "pinnacle_gate": {"ready": True, "blockers": []},
        "decision_bundle_id": "bundle-test",
        "official_snapshot": {
            "snapshot_id": "pinnacle-run-id",
            "retrieved_at": now,
            "bootstrap_sha256": bootstrap,
            "fixtures_sha256": fixtures,
        },
        "gameweeks": [1, 2, 3],
        "robust_cvar_scenarios": {"unrestricted": {"status": "Optimal"}},
        "selection_regret": [{"player_id": 1, "regret": 1.0}],
        "solver_parity": {"comparison_surface": "pinnacle_ev"},
        "authoritative_decision": {
            "contract": "apex-exact-horizon-decision-v1",
            "status": "Optimal",
            "objective": 102.0,
            "objective_reconciliation": 102.0,
            "solution": exact_solution,
            "weeks": [{"gw": 1, **_mechanics("ExactCap")}],
            "shortlist": {"candidate_count": 4},
            "equivalence": {"unique_optimum_proven": False},
        },
    }


def _elite(converged: bool, bootstrap: str = "boot", fixtures: str = "fix") -> dict:
    return {
        "contract": "elite-test",
        "safe_to_act": True,
        "full_apex_ready": True,
        "decision_bundle_id": "bundle-test",
        "official_snapshot": {
            "snapshot_id": "elite-run-id",
            "bootstrap_sha256": bootstrap,
            "fixtures_sha256": fixtures,
        },
        "epsilon_convergence": {"converged": converged},
        "epsilon_sensitivity": [],
        "scenarios": {},
    }


def _run(tmp_path: Path, pinnacle: dict, elite: dict) -> tuple[subprocess.CompletedProcess, dict]:
    pinnacle_path = tmp_path / "pinnacle.json"
    elite_path = tmp_path / "elite.json"
    output_dir = tmp_path / "out"
    pinnacle_path.write_text(json.dumps(pinnacle), encoding="utf-8")
    elite_path.write_text(json.dumps(elite), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_canonical_recommendation.py",
            "--pinnacle",
            str(pinnacle_path),
            "--elite",
            str(elite_path),
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    payload = json.loads(
        (output_dir / "apex_recommendation_latest.json").read_text(encoding="utf-8")
    )
    return result, payload


def test_green_base_is_staging_only_even_when_elite_converges(tmp_path: Path) -> None:
    result, payload = _run(tmp_path, _pinnacle(), _elite(True))
    assert result.returncode == 0
    assert payload["strategy_base_ready"] is True
    assert payload["strategy_stage"] == "base_validated"
    assert payload["ready_to_act"] is False
    assert payload["recommendation"] is None
    assert payload["contract"] == "apex-strategy-recommendation-v3"
    assert payload["internal_diagnostics"]["same_official_surface"] is True
    exact = payload["internal_diagnostics"]["exact_horizon_staging"]
    assert exact["authority"] is False
    assert exact["solution"]["status"] == "Optimal"


def test_unstable_elite_cannot_create_an_intermediate_team(tmp_path: Path) -> None:
    result, payload = _run(tmp_path, _pinnacle(), _elite(False))
    assert result.returncode == 0
    assert payload["strategy_base_ready"] is True
    assert payload["ready_to_act"] is False
    assert payload["recommendation"] is None


def test_mismatched_official_surface_blocks_staging(tmp_path: Path) -> None:
    result, payload = _run(tmp_path, _pinnacle(), _elite(True, fixtures="different"))
    assert result.returncode == 2
    assert payload["strategy_base_ready"] is False
    assert payload["ready_to_act"] is False
    assert payload["recommendation"] is None
    assert any("content hashes do not match" in blocker for blocker in payload["blockers"])


def test_mismatched_decision_bundle_blocks_staging(tmp_path: Path) -> None:
    pinnacle = _pinnacle()
    elite = _elite(True)
    pinnacle["decision_bundle_id"] = "bundle-a"
    elite["decision_bundle_id"] = "bundle-b"
    result, payload = _run(tmp_path, pinnacle, elite)
    assert result.returncode == 2
    assert payload["strategy_base_ready"] is False
    assert payload["ready_to_act"] is False
    assert any("bundle identities do not match" in blocker for blocker in payload["blockers"])


def test_staging_answer_context_is_explicitly_non_actionable(tmp_path: Path) -> None:
    result, payload = _run(tmp_path, _pinnacle(), _elite(False))
    context = json.loads(
        (tmp_path / "out" / "apex_answer_context.json").read_text(encoding="utf-8")
    )
    markdown = (tmp_path / "out" / "apex_recommendation_latest.md").read_text(
        encoding="utf-8"
    )
    assert result.returncode == 0
    assert payload["ready_to_act"] is False
    assert context["safe_to_act"] is False
    assert "final adaptive/receding-horizon strategy selector not yet applied" in context[
        "blockers"
    ]
    assert "STAGING" in markdown
    assert "Captain:" not in markdown
