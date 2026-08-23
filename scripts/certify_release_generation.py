from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apex_fpl.services.release_profile import (
    INSEASON_PROFILE,
    LAUNCH_PROFILE,
    resolve_release_profile,
)


CONTRACT = "apex-release-generation-certificate-v2"
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


def _validate_sensitivity(profile, sensitivity: dict[str, Any], bundle_id: str) -> dict[str, Any]:
    if sensitivity.get("decision_bundle_id") != bundle_id:
        raise ValueError("lifecycle sensitivity artifact does not match decision_bundle_id")
    if profile == LAUNCH_PROFILE:
        if sensitivity.get("contract") != LAUNCH_PROFILE.sensitivity_contract:
            raise ValueError("launch release requires the launch adversarial sensitivity contract")
        summary = sensitivity.get("summary") or {}
        if summary.get("audit_complete") is not True:
            raise ValueError("launch adversarial selection sensitivity audit is incomplete")
        if summary.get("search_surface_defect_signals"):
            raise ValueError("launch adversarial sensitivity found search-surface defect signals")
        if summary.get("ban_solve_errors"):
            raise ValueError("launch adversarial sensitivity contains solve errors")
        return {"contract": sensitivity.get("contract"), "ready": True}

    if profile == INSEASON_PROFILE:
        if sensitivity.get("contract") != INSEASON_PROFILE.sensitivity_contract:
            raise ValueError("in-season release requires the transfer-action sensitivity contract")
        if sensitivity.get("selector") != INSEASON_PROFILE.selector:
            raise ValueError("in-season sensitivity selector does not match release selector")
        if sensitivity.get("ready") is not True or sensitivity.get("blockers"):
            raise ValueError(
                "in-season action sensitivity is not ready: "
                + "; ".join(str(row) for row in sensitivity.get("blockers") or [])
            )
        return {
            "contract": sensitivity.get("contract"),
            "ready": True,
            "published_action": sensitivity.get("published_action"),
            "baseline": sensitivity.get("baseline"),
            "counterfactuals": sensitivity.get("counterfactuals") or [],
        }

    raise ValueError(f"unsupported release profile: {profile}")


def validate_release_payloads(
    *,
    recommendation_payload: dict[str, Any],
    answer_context: dict[str, Any],
    pinnacle: dict[str, Any],
    parity: dict[str, Any],
    sensitivity: dict[str, Any],
    bench_stress: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Validate one sealed generation against its selector-specific release profile."""
    bundle_id = str(recommendation_payload.get("decision_bundle_id") or "")
    if not bundle_id:
        raise ValueError("canonical recommendation has no decision_bundle_id")
    recommendation = recommendation_payload.get("recommendation") or {}
    profile = resolve_release_profile(recommendation, manifest)

    surfaces = {
        "manifest": manifest.get("bundle_id"),
        "answer_context": answer_context.get("decision_bundle_id"),
        "pinnacle": pinnacle.get("decision_bundle_id"),
        "solver_parity": parity.get("decision_bundle_id"),
        "sensitivity": sensitivity.get("decision_bundle_id"),
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
    for field in (
        "hard_fact_coverage",
        "canonical_projection_pair_coverage",
        "airsenal_projection_pair_coverage",
    ):
        if abs(float(truth.get(field, 0.0)) - 1.0) > 1e-12:
            raise ValueError(f"certified all-player truth coverage is incomplete: {field}")

    parity_surface = parity.get("comparison_surface")
    if parity_surface != "pinnacle_ev":
        raise ValueError(f"solver parity comparison surface is not pinnacle_ev: {parity_surface!r}")

    sensitivity_summary = _validate_sensitivity(profile, sensitivity, bundle_id)
    if bench_stress.get("contract") != "apex-bench-stress-v2":
        raise ValueError("release requires selector-neutral canonical bench stress v2")
    if bench_stress.get("selector") != recommendation.get("selector"):
        raise ValueError("bench-stress selector does not match canonical selector")
    if bench_stress.get("fixed_submission") is not True:
        raise ValueError("submitted-bench stress did not preserve a fixed submission")
    if bench_stress.get("bench_reordered_with_hindsight") is not False:
        raise ValueError("submitted-bench stress reordered the bench with hindsight")

    selector = str(recommendation.get("selector") or "")
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
    if profile == INSEASON_PROFILE:
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
        "lifecycle": profile.name,
        "sensitivity": sensitivity_summary,
        "mechanics": mechanics,
        "truth_player_count": int(truth.get("player_count") or 0),
        "bench_stress_fixed_submission": True,
    }


def _run(*args: str) -> None:
    subprocess.run([sys.executable, *args], check=True)


def _write_certificate(run_dir: Path, certificate: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "release_generation_certificate.json").write_text(
        json.dumps(certificate, indent=2) + "\n", encoding="utf-8"
    )


def certify_generation(
    *,
    run_dir: Path,
    bundle_dir: Path,
    promotion_dir: Path,
    run_id: str,
) -> dict[str, Any]:
    certificate: dict[str, Any] = {
        "contract": CONTRACT,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": str(run_id),
        "ready": False,
        "decision_bundle_id": None,
        "selector": None,
        "lifecycle": None,
        "gates": {
            "profile": "pending",
            "sensitivity": "pending",
            "bench_stress": "pending",
            "cross_artifact_validation": "pending",
            "dry_run_promotion": "pending",
        },
        "blockers": [],
        "warnings": [],
        "dry_run_promotion_validated": False,
    }
    _write_certificate(run_dir, certificate)

    try:
        canonical_path = run_dir / "apex_recommendation_latest.json"
        canonical = _load(canonical_path)
        bundle_manifest = _load(bundle_dir / "manifest.json")
        bundle_id = str(bundle_manifest.get("bundle_id") or "")
        if not bundle_id:
            raise ValueError("DecisionBundle manifest has no bundle_id")
        recommendation = canonical.get("recommendation") or {}
        profile = resolve_release_profile(recommendation, bundle_manifest)
        certificate.update(
            {
                "decision_bundle_id": bundle_id,
                "selector": recommendation.get("selector"),
                "lifecycle": profile.name,
            }
        )
        certificate["gates"]["profile"] = "passed"
        _write_certificate(run_dir, certificate)

        if profile == LAUNCH_PROFILE:
            sensitivity_path = run_dir / "adversarial_launch_bans.json"
            _run(
                "scripts/run_adversarial_launch_ban.py",
                "--bundle-dir",
                str(bundle_dir),
                "--canonical",
                str(canonical_path),
                "--output",
                str(sensitivity_path),
                "--csv",
                str(run_dir / "adversarial_launch_bans.csv"),
            )
            _run(
                "scripts/certify_adversarial_launch_ban.py",
                str(sensitivity_path),
                "--decision-bundle-id",
                bundle_id,
            )
        elif profile == INSEASON_PROFILE:
            sensitivity_path = run_dir / "inseason_action_sensitivity.json"
            _run(
                "scripts/audit_inseason_action_sensitivity.py",
                "--bundle-dir",
                str(bundle_dir),
                "--canonical",
                str(canonical_path),
                "--output",
                str(sensitivity_path),
            )
        else:  # pragma: no cover - resolve_release_profile is exhaustive
            raise ValueError(f"unsupported release profile: {profile}")
        sensitivity = _load(sensitivity_path)
        certificate["gates"]["sensitivity"] = "passed"
        certificate["warnings"].extend(str(row) for row in sensitivity.get("warnings") or [])
        _write_certificate(run_dir, certificate)

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
        bench_stress = _load(run_dir / "bench_stress.json")
        certificate["gates"]["bench_stress"] = "passed"
        _write_certificate(run_dir, certificate)

        summary = validate_release_payloads(
            recommendation_payload=canonical,
            answer_context=_load(run_dir / "apex_answer_context.json"),
            pinnacle=_load(run_dir / "pinnacle_latest.json"),
            parity=_load(run_dir / "solver_parity.json"),
            sensitivity=sensitivity,
            bench_stress=bench_stress,
            manifest=bundle_manifest,
        )
        certificate.update(summary)
        certificate["gates"]["cross_artifact_validation"] = "passed"
        _write_certificate(run_dir, certificate)

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
        certificate["gates"]["dry_run_promotion"] = "passed"
        certificate["dry_run_promotion_validated"] = True
        certificate["certified_generation_artifact"] = "dry_run_certified_generation.json"
        certificate["ready"] = True
        certificate["generated_at"] = datetime.now(timezone.utc).isoformat()
        certificate["warnings"] = list(dict.fromkeys(certificate.get("warnings") or []))
        _write_certificate(run_dir, certificate)
        return certificate
    except Exception as exc:
        certificate["blockers"] = list(
            dict.fromkeys([*(certificate.get("blockers") or []), f"{type(exc).__name__}: {exc}"])
        )
        certificate["generated_at"] = datetime.now(timezone.utc).isoformat()
        _write_certificate(run_dir, certificate)
        return certificate


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run lifecycle-aware sensitivity, bench, mechanics and dry-run promotion certification."
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
    if certificate.get("ready") is not True:
        raise SystemExit(
            "release generation is not certified: "
            + "; ".join(str(row) for row in certificate.get("blockers") or [])
        )


if __name__ == "__main__":
    main()
