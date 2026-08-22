from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONTRACT = "apex-release-generation-certificate-v1"
FINAL_SELECTORS = {
    "adaptive_gw1_launch_with_transfer_option_value",
    "receding_horizon_current_team_maximum_ev",
}
EXACT_ACTION_AUTHORITY = "independent_exact_current_gameweek_rescore"


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"required release artifact is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"release artifact is not an object: {path}")
    return payload


def _record_ids(records: Any, *, expected: int | None = None) -> list[int]:
    if not isinstance(records, list):
        raise ValueError("player record surface is not a list")
    ids: list[int] = []
    for row in records:
        if not isinstance(row, dict) or row.get("player_id") is None:
            raise ValueError("player record surface contains a row without player_id")
        ids.append(int(row["player_id"]))
    if expected is not None and len(ids) != expected:
        raise ValueError(f"player record surface has {len(ids)} rows, expected {expected}")
    if len(ids) != len(set(ids)):
        raise ValueError("player record surface contains duplicate player identities")
    return ids


def validate_release_payloads(
    *,
    recommendation_payload: dict[str, Any],
    answer_context: dict[str, Any],
    pinnacle: dict[str, Any],
    parity: dict[str, Any],
    adversarial: dict[str, Any],
    bench_stress: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Validate one sealed generation as a release candidate.

    This is intentionally independent from the producer-side checks. A release cannot
    be certified merely because each individual producer wrote a green flag; the
    artifacts must agree on bundle identity, actionable mechanics, truth readiness,
    adversarial sensitivity and submitted-bench semantics.
    """
    bundle_id = str(recommendation_payload.get("decision_bundle_id") or "")
    if not bundle_id:
        raise ValueError("canonical recommendation has no decision_bundle_id")
    surfaces = {
        "manifest": manifest.get("bundle_id"),
        "answer_context": answer_context.get("decision_bundle_id"),
        "pinnacle": pinnacle.get("decision_bundle_id"),
        "solver_parity": parity.get("decision_bundle_id"),
        "adversarial": adversarial.get("decision_bundle_id"),
        "bench_stress": bench_stress.get("decision_bundle_id"),
    }
    mismatched = {name: value for name, value in surfaces.items() if value != bundle_id}
    if mismatched:
        raise ValueError(f"release surfaces disagree on decision_bundle_id: {mismatched}")

    if recommendation_payload.get("strategy_stage") != "final_validated":
        raise ValueError("canonical strategy_stage is not final_validated")
    if recommendation_payload.get("strategy_base_ready") is not True:
        raise ValueError("canonical strategy base is not ready")
    if recommendation_payload.get("ready_to_act") is not True:
        raise ValueError("canonical recommendation is not ready_to_act")
    if answer_context.get("safe_to_act") is not True or answer_context.get("ready_to_act") is not True:
        raise ValueError("answer context is not safe/ready to act")
    if answer_context.get("blockers"):
        raise ValueError(f"answer context contains blockers: {answer_context['blockers']}")
    if pinnacle.get("pinnacle_ready") is not True:
        raise ValueError("Pinnacle is not ready")

    truth = recommendation_payload.get("all_player_truth") or {}
    if truth.get("ready") is not True or truth.get("blockers"):
        raise ValueError(f"all-player truth is not ready: {truth.get('blockers') or []}")
    for field in ("hard_fact_coverage", "canonical_projection_pair_coverage", "airsenal_projection_pair_coverage"):
        if abs(float(truth.get(field, 0.0)) - 1.0) > 1e-12:
            raise ValueError(f"certified all-player truth coverage is incomplete: {field}")

    parity_surface = parity.get("comparison_surface")
    if parity_surface != "pinnacle_ev":
        raise ValueError(f"solver parity comparison surface is not pinnacle_ev: {parity_surface!r}")

    bans_summary = adversarial.get("summary") or {}
    if bans_summary.get("audit_complete") is not True:
        raise ValueError("adversarial selection sensitivity audit is incomplete")
    if bans_summary.get("search_surface_defect_signals"):
        raise ValueError("adversarial selection sensitivity found search-surface defect signals")
    if bans_summary.get("ban_solve_errors"):
        raise ValueError("adversarial selection sensitivity contains solve errors")
    if bench_stress.get("fixed_submission") is not True:
        raise ValueError("submitted-bench stress did not preserve a fixed submission")
    if bench_stress.get("bench_reordered_with_hindsight") is not False:
        raise ValueError("submitted-bench stress reordered the bench with hindsight")

    recommendation = recommendation_payload.get("recommendation") or {}
    selector = str(recommendation.get("selector") or "")
    if selector not in FINAL_SELECTORS:
        raise ValueError(f"release selector is not a final selector: {selector!r}")
    squad_ids = _record_ids(recommendation.get("squad"), expected=15)
    xi_ids = _record_ids(recommendation.get("xi"), expected=11)
    if not set(xi_ids).issubset(squad_ids):
        raise ValueError("canonical XI is not a subset of canonical squad")
    captain_id = int(recommendation["captain_id"])
    vice_id = int(recommendation["vice_captain_id"])
    if captain_id == vice_id or captain_id not in xi_ids or vice_id not in xi_ids:
        raise ValueError("canonical captain/vice mechanics are invalid")

    mechanics: dict[str, Any] = {
        "selector": selector,
        "squad_ids": squad_ids,
        "xi_ids": xi_ids,
        "captain_id": captain_id,
        "vice_captain_id": vice_id,
    }
    if selector == "receding_horizon_current_team_maximum_ev":
        action = recommendation.get("action_now")
        if not isinstance(action, dict):
            raise ValueError("receding-horizon recommendation has no executable action_now")
        if action.get("mechanics_reconciled") is not True:
            raise ValueError("action_now mechanics are not independently reconciled")
        if action.get("mechanics_authority") != EXACT_ACTION_AUTHORITY:
            raise ValueError("action_now mechanics authority is not the independent exact rescore")

        action_squad_ids = _record_ids(action.get("squad"), expected=15)
        action_xi_ids = _record_ids(action.get("xi"), expected=11)
        if set(action_squad_ids) != set(squad_ids):
            raise ValueError("action_now squad identities do not match canonical squad")
        if action_xi_ids != xi_ids:
            raise ValueError("action_now XI does not match canonical exact-rescored XI")
        action_captain = _record_ids(action.get("captain"), expected=1)[0]
        action_vice = _record_ids(action.get("vice_captain"), expected=1)[0]
        if action_captain != captain_id:
            raise ValueError("action_now captain does not match canonical exact-rescored captain")
        if action_vice != vice_id:
            raise ValueError("action_now vice-captain does not match canonical exact-rescored vice-captain")
        bench_gk = action.get("bench_gk")
        if not isinstance(bench_gk, dict) or bench_gk.get("player_id") is None:
            raise ValueError("action_now bench goalkeeper is missing")
        action_bench_gk = int(bench_gk["player_id"])
        canonical_bench_gk = int(recommendation["bench_gk_id"])
        if action_bench_gk != canonical_bench_gk:
            raise ValueError("action_now bench goalkeeper does not match canonical mechanics")
        action_bench = _record_ids(action.get("outfield_bench_order"), expected=3)
        canonical_bench = [int(value) for value in recommendation.get("outfield_bench_order_ids") or []]
        if action_bench != canonical_bench:
            raise ValueError("action_now outfield bench order does not match canonical mechanics")
        if abs(
            float(action["exact_expected_total_points"])
            - float(recommendation["gw1_expected_total_with_mechanics"])
        ) > 1e-9:
            raise ValueError("action_now exact expected points do not match canonical mechanics")
        mechanics.update(
            {
                "action_squad_ids": action_squad_ids,
                "action_xi_ids": action_xi_ids,
                "action_captain_id": action_captain,
                "action_vice_captain_id": action_vice,
                "bench_gk_id": action_bench_gk,
                "outfield_bench_order_ids": action_bench,
                "exact_expected_total_points": float(action["exact_expected_total_points"]),
            }
        )

    evidence = recommendation_payload.get("final_selected_player_evidence") or {}
    if evidence.get("contract") != "apex-player-evidence-v2":
        raise ValueError("final selected-player evidence contract is not v2")
    coverage = evidence.get("coverage") or {}
    if coverage.get("ready") is not True:
        raise ValueError("final selected-player evidence coverage is not ready")
    dossier_ids = _record_ids(evidence.get("dossiers"), expected=15)
    if set(dossier_ids) != set(squad_ids):
        raise ValueError("final player-evidence dossiers do not match canonical squad identities")

    return {
        "decision_bundle_id": bundle_id,
        "selector": selector,
        "mechanics": mechanics,
        "truth_player_count": int(truth.get("player_count") or 0),
        "adversarial_audit_complete": True,
        "bench_stress_fixed_submission": True,
    }


def _run(*args: str) -> None:
    subprocess.run([sys.executable, *args], check=True)


def certify_generation(
    *,
    run_dir: Path,
    bundle_dir: Path,
    promotion_dir: Path,
    run_id: str,
) -> dict[str, Any]:
    canonical_path = run_dir / "apex_recommendation_latest.json"
    bundle_manifest = _load(bundle_dir / "manifest.json")
    bundle_id = str(bundle_manifest.get("bundle_id") or "")
    if not bundle_id:
        raise ValueError("DecisionBundle manifest has no bundle_id")

    _run(
        "scripts/run_adversarial_launch_ban.py",
        "--bundle-dir",
        str(bundle_dir),
        "--canonical",
        str(canonical_path),
        "--output",
        str(run_dir / "adversarial_launch_bans.json"),
        "--csv",
        str(run_dir / "adversarial_launch_bans.csv"),
    )
    _run(
        "scripts/certify_adversarial_launch_ban.py",
        str(run_dir / "adversarial_launch_bans.json"),
        "--decision-bundle-id",
        bundle_id,
    )
    _run(
        "scripts/audit_bench_stress.py",
        "--bundle-dir",
        str(bundle_dir),
        "--canonical",
        str(canonical_path),
        "--output",
        str(run_dir / "bench_stress.json"),
        "--csv",
        str(run_dir / "bench_stress.csv"),
    )

    summary = validate_release_payloads(
        recommendation_payload=_load(canonical_path),
        answer_context=_load(run_dir / "apex_answer_context.json"),
        pinnacle=_load(run_dir / "pinnacle_latest.json"),
        parity=_load(run_dir / "solver_parity.json"),
        adversarial=_load(run_dir / "adversarial_launch_bans.json"),
        bench_stress=_load(run_dir / "bench_stress.json"),
        manifest=bundle_manifest,
    )

    if promotion_dir.exists():
        shutil.rmtree(promotion_dir)
    _run(
        "scripts/promote_certified_generation.py",
        "--run-dir",
        str(run_dir),
        "--bundle-dir",
        str(bundle_dir),
        "--target-dir",
        str(promotion_dir),
        "--run-id",
        str(run_id),
    )
    promoted = promotion_dir / "certified_generation.json"
    if not promoted.is_file():
        raise ValueError("dry-run production promotion did not produce certified_generation.json")
    shutil.copy2(promoted, run_dir / "dry_run_certified_generation.json")

    certificate = {
        "contract": CONTRACT,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": str(run_id),
        **summary,
        "dry_run_promotion_validated": True,
        "certified_generation_artifact": "dry_run_certified_generation.json",
    }
    (run_dir / "release_generation_certificate.json").write_text(
        json.dumps(certificate, indent=2) + "\n",
        encoding="utf-8",
    )
    return certificate


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run adversarial, bench-stress, mechanics and dry-run promotion release certification."
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--promotion-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    certificate = certify_generation(
        run_dir=args.run_dir,
        bundle_dir=args.bundle_dir,
        promotion_dir=args.promotion_dir,
        run_id=args.run_id,
    )
    print(json.dumps(certificate, indent=2))


if __name__ == "__main__":
    main()
