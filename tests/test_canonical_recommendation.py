from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys


def _rows() -> list[dict]:
    rows = []
    positions = ["GK", "GK", "DEF", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "MID", "FWD", "FWD", "FWD"]
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
                "tactical_role_source": "verified_lineup",
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
        "sources": [
            {
                "name": "news_feeds",
                "ok": True,
                "configured": True,
                "checked_at": now,
                "version": "test",
            }
        ],
        "robust_cvar_scenarios": {"unrestricted": {"status": "Optimal"}},
        "deterministic_scenarios": {"unrestricted": _solution("StrategyCap", 101.0)},
        "gw1_mechanics": {"unrestricted": _mechanics("StrategyCap")},
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
        "selected_player_evidence": {
            "contract": "apex-player-evidence-v1",
            "coverage": {
                "selected_players": 15,
                "selected_players_with_current_evidence": 1,
                "relevant_evidence_rows": 1,
                "captain_id": 1,
                "captain_has_current_evidence": True,
                "high_uncertainty_starter_ids": [],
                "high_uncertainty_starters_missing_evidence": [],
                "ready": True,
            },
            "dossiers": [
                {
                    "player_id": row["player_id"],
                    "is_captain": row["player_id"] == 1,
                    "has_current_decision_evidence": row["player_id"] == 1,
                    "current_evidence_count": 1 if row["player_id"] == 1 else 0,
                    "evidence": [],
                }
                for row in _rows()
            ],
        },
        "selection_regret": [{"player_id": row["player_id"], "regret": 1.0} for row in _rows()],
        "solver_parity": {
            "comparison_surface": "pinnacle_ev",
            "decision_bundle_id": "bundle-test",
            "official_snapshot": {
                "bootstrap_sha256": bootstrap,
                "fixtures_sha256": fixtures,
            },
        },
        "initial_squad_contingencies": {"status": "Optimal"},
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
        "maximum_ev_reference": _solution("MaxCap", 100.0),
        "maximum_ev_gw1_mechanics": _mechanics("MaxCap"),
        "elite": _solution("EliteCap", 99.7),
        "elite_gw1_mechanics": _mechanics("EliteCap"),
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
    payload = json.loads((output_dir / "apex_recommendation_latest.json").read_text(encoding="utf-8"))
    return result, payload


def test_converged_elite_remains_diagnostic_only(tmp_path: Path) -> None:
    result, payload = _run(tmp_path, _pinnacle(), _elite(True))
    assert result.returncode == 0
    assert payload["ready_to_act"] is True
    assert payload["contract"] == "apex-strategy-recommendation-v2"
    assert payload["recommendation"]["selector"] == "exact_horizon_maximum_ev"
    assert payload["recommendation"]["captain"] == "ExactCap"
    assert payload["internal_diagnostics"]["same_official_surface"] is True


def test_unstable_elite_cannot_change_strategy_authority(tmp_path: Path) -> None:
    result, payload = _run(tmp_path, _pinnacle(), _elite(False))
    assert result.returncode == 0
    assert payload["ready_to_act"] is True
    assert payload["recommendation"]["selector"] == "exact_horizon_maximum_ev"
    assert payload["recommendation"]["captain"] == "ExactCap"


def test_mismatched_official_surface_withholds_recommendation(tmp_path: Path) -> None:
    result, payload = _run(tmp_path, _pinnacle(), _elite(True, fixtures="different"))
    assert result.returncode == 2
    assert payload["ready_to_act"] is False
    assert payload["recommendation"] is None
    assert any("content hashes do not match" in blocker for blocker in payload["blockers"])


def test_mismatched_decision_bundle_withholds_recommendation(tmp_path: Path) -> None:
    pinnacle = _pinnacle()
    elite = _elite(True)
    pinnacle["decision_bundle_id"] = "bundle-a"
    elite["decision_bundle_id"] = "bundle-b"
    result, payload = _run(tmp_path, pinnacle, elite)
    assert result.returncode == 2
    assert payload["ready_to_act"] is False
    assert any("bundle identities do not match" in blocker for blocker in payload["blockers"])


def test_answer_context_block_returns_nonzero_and_withheld_markdown(tmp_path: Path) -> None:
    pinnacle = _pinnacle()
    pinnacle["solver_parity"] = None
    result, payload = _run(tmp_path, pinnacle, _elite(False))
    markdown = (tmp_path / "out" / "apex_recommendation_latest.md").read_text(encoding="utf-8")
    assert result.returncode == 2
    assert payload["ready_to_act"] is False
    assert payload["recommendation"] is None
    assert "NOT READY" in markdown
    assert "Captain:" not in markdown
