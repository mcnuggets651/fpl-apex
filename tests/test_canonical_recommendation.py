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
    return {
        "contract": "pinnacle-test",
        "safe_to_act": True,
        "full_apex_ready": True,
        "pinnacle_ready": True,
        "pinnacle_gate": {"ready": True, "blockers": []},
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
        "selection_regret": [{"player_id": row["player_id"], "regret": 1.0} for row in _rows()],
        "solver_parity": {"comparison_surface": "pinnacle_ev"},
        "initial_squad_contingencies": {"status": "Optimal"},
    }


def _elite(converged: bool, bootstrap: str = "boot", fixtures: str = "fix") -> dict:
    return {
        "contract": "elite-test",
        "safe_to_act": True,
        "full_apex_ready": True,
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


def test_converged_elite_becomes_canonical(tmp_path: Path) -> None:
    result, payload = _run(tmp_path, _pinnacle(), _elite(True))
    assert result.returncode == 0
    assert payload["ready_to_act"] is True
    assert payload["recommendation"]["selector"] == "elite_lexicographic"
    assert payload["recommendation"]["captain"] == "EliteCap"
    assert payload["internal_diagnostics"]["same_official_surface"] is True


def test_unstable_elite_falls_back_to_max_ev(tmp_path: Path) -> None:
    result, payload = _run(tmp_path, _pinnacle(), _elite(False))
    assert result.returncode == 0
    assert payload["ready_to_act"] is True
    assert payload["recommendation"]["selector"] == "maximum_ev"
    assert payload["recommendation"]["captain"] == "MaxCap"


def test_mismatched_official_surface_withholds_recommendation(tmp_path: Path) -> None:
    result, payload = _run(tmp_path, _pinnacle(), _elite(True, fixtures="different"))
    assert result.returncode == 2
    assert payload["ready_to_act"] is False
    assert any("content hashes do not match" in blocker for blocker in payload["blockers"])
