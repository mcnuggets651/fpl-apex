#!/usr/bin/env python3
"""Run final promotion with stability correction and football-reality gating.

The canonical optimiser remains unchanged. After it produces the final squad this
wrapper applies a non-mutating selection-reality audit. A candidate that is
mathematically optimal but structurally fragile (for example an unusable first
bench, unresolved specialist XI conflict, or high transfer risk) is withheld rather
than published as actionable.
"""
from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import pandas as pd

import apex_fpl.services.joint_initial_path as joint
from apex_fpl.services.decision_bundle import DecisionBundle
from apex_fpl.services.finalized_stability import optimise_with_bounded_stability_retry
from apex_fpl.services.selection_reality import audit_selected_squad_reality


def _frame_if_present(path: Path) -> pd.DataFrame | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        return pd.read_csv(path)
    except Exception:
        return None


def _cli_path(flag: str, default: str) -> Path:
    try:
        index = sys.argv.index(flag)
    except ValueError:
        return Path(default)
    if index + 1 >= len(sys.argv):
        raise SystemExit(f"{flag} requires a value")
    return Path(sys.argv[index + 1])


def _ids_from_rows(rows: list[dict]) -> set[int]:
    return {
        int(row["player_id"])
        for row in rows
        if isinstance(row, dict) and row.get("player_id") is not None
    }


def _bench_ids(rec: dict, squad: list[dict], xi_ids: set[int]) -> list[int]:
    explicit = rec.get("outfield_bench_order_ids") or []
    if explicit:
        return [int(pid) for pid in explicit]
    by_name = {
        str(row.get("web_name") or ""): int(row["player_id"])
        for row in squad
        if row.get("player_id") is not None
    }
    ordered = []
    for name in rec.get("outfield_bench_order") or []:
        if str(name) in by_name:
            ordered.append(by_name[str(name)])
    if ordered:
        return ordered
    return [
        int(row["player_id"])
        for row in squad
        if row.get("player_id") is not None and int(row["player_id"]) not in xi_ids
    ]


def _withhold_for_reality(
    payload: dict,
    blockers: tuple[str, ...],
    warnings: tuple[str, ...],
    report: pd.DataFrame,
    *,
    output_dir: Path,
) -> None:
    diagnostics = payload.setdefault("internal_diagnostics", {})
    diagnostics["selection_reality"] = {
        "contract": "apex-selection-reality-v1",
        "ready": False,
        "blockers": list(blockers),
        "warnings": list(warnings),
        "rows": json.loads(report.to_json(orient="records")),
    }
    payload["ready_to_act"] = False
    payload["safe_to_act"] = False
    payload["blockers"] = list(
        dict.fromkeys((payload.get("blockers") or []) + list(blockers))
    )
    payload["warnings"] = list(
        dict.fromkeys((payload.get("warnings") or []) + list(warnings))
    )
    payload["recommendation"] = None
    (output_dir / "apex_recommendation_latest.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    (output_dir / "apex_recommendation_latest.md").write_text(
        "# Apex Unified Recommendation — NOT READY\n\n"
        + "\n".join(f"- {row}" for row in payload["blockers"])
        + "\n",
        encoding="utf-8",
    )
    context_path = output_dir / "apex_answer_context.json"
    if context_path.exists():
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["safe_to_act"] = False
        context["ready_to_act"] = False
        context["production_result"] = None
        context["blockers"] = list(payload["blockers"])
        context["warnings"] = list(payload["warnings"])
        context.setdefault("diagnostics", {})["selection_reality"] = diagnostics[
            "selection_reality"
        ]
        context_path.write_text(json.dumps(context, indent=2), encoding="utf-8")


def _audit_final_selection(*, output_dir: Path, bundle_dir: Path) -> None:
    recommendation_path = output_dir / "apex_recommendation_latest.json"
    if not recommendation_path.exists():
        raise SystemExit("selection reality gate requires canonical recommendation output")
    payload = json.loads(recommendation_path.read_text(encoding="utf-8"))
    if payload.get("ready_to_act") is not True:
        return
    rec = payload.get("recommendation") or {}
    squad = rec.get("squad") or []
    xi = rec.get("xi") or []
    if len(squad) != 15 or len(xi) != 11:
        raise SystemExit("selection reality gate requires exact final 15/XI")

    selected_ids = _ids_from_rows(squad)
    xi_ids = _ids_from_rows(xi)
    bench_ids = _bench_ids(rec, squad, xi_ids)

    # Audit the exact sealed player surface used by the optimiser, not the rendered
    # recommendation rows. Rendered rows are an output contract and may omit columns
    # such as appearance_probability; treating an omitted field as zero would create
    # a false readiness failure (or, worse, a selector-dependent gate).
    bundle = DecisionBundle.load(bundle_dir)
    players = bundle.to_pipeline_output().players.copy()
    if "player_id" not in players.columns:
        raise SystemExit("selection reality gate requires player_id on sealed player surface")
    players = players[players["player_id"].astype(int).isin(selected_ids)].copy()
    sealed_ids = set(players["player_id"].astype(int))
    if sealed_ids != selected_ids or len(players) != 15:
        raise SystemExit("selection reality gate selected IDs do not reconcile to sealed player surface")

    result = audit_selected_squad_reality(
        players,
        selected_ids=selected_ids,
        xi_ids=xi_ids,
        bench_ids=bench_ids,
        specialist_report=_frame_if_present(output_dir / "specialist_disagreement.csv"),
        hierarchy_evidence=_frame_if_present(Path("data/manual/squad_hierarchy.csv")),
        transfer_report=_frame_if_present(output_dir / "transfer_intelligence.csv"),
    )
    payload.setdefault("internal_diagnostics", {})["selection_reality"] = {
        "contract": "apex-selection-reality-v1",
        "ready": result.ready_for_high_confidence,
        "blockers": list(result.blockers),
        "warnings": list(result.warnings),
        "playable_outfield_bench": result.playable_outfield_bench,
        "source_surface": "sealed_decision_bundle_players",
        "rows": json.loads(result.report.to_json(orient="records")),
    }
    if not result.ready_for_high_confidence:
        _withhold_for_reality(
            payload,
            result.blockers,
            result.warnings,
            result.report,
            output_dir=output_dir,
        )
        raise SystemExit("selected-squad football reality gate is not ready")
    recommendation_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    original = joint.optimise_joint_initial_path

    def corrected(*args, **kwargs):
        return optimise_with_bounded_stability_retry(original, *args, **kwargs)

    joint.optimise_joint_initial_path = corrected
    runpy.run_path("scripts/apply_joint_path_promotion.py", run_name="__main__")
    _audit_final_selection(
        output_dir=_cli_path("--output-dir", "data/generated"),
        bundle_dir=_cli_path("--bundle-dir", "data/generated/decision_bundle"),
    )


if __name__ == "__main__":
    main()
