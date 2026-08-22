#!/usr/bin/env python3
"""Run final promotion with stability correction and football-reality gating.

The final wrapper is deliberately non-mutating with respect to FPL mechanics. The
canonical selector must already have produced a legal current XI, captain/vice and
bench order. This wrapper independently recomputes exact mechanics from the sealed
DecisionBundle and refuses publication unless the submitted identities and expected
points reconcile exactly. It then applies the non-mutating football-reality audit.
"""
from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import pandas as pd

import apex_fpl.services.joint_initial_path as joint
from apex_fpl.optimisation.bench_policy import (
    FIRST_BENCH_MIN_APPEARANCE,
    FIRST_BENCH_MIN_EXPECTED_MINUTES,
)
from apex_fpl.optimisation.exact_decision import optimise_fixed_squad_gameweek
from apex_fpl.services.decision_bundle import DecisionBundle
from apex_fpl.services.decision_eligibility import (
    captain_eligible_ids,
    evidence_eligibility,
)
from apex_fpl.services.finalized_stability import optimise_with_bounded_stability_retry
from apex_fpl.services.hierarchy_evidence import load_current_hierarchy_evidence
from apex_fpl.services.selection_reality import audit_selected_squad_reality


def _frame_if_present(path: Path) -> pd.DataFrame | None:
    """Load an optional generated CSV; malformed present files are fatal."""
    if not path.exists() or path.stat().st_size == 0:
        return None
    return pd.read_csv(path)


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


def _unique_name_id(rows: list[dict], name: str | None, label: str) -> int:
    if not name:
        raise SystemExit(f"selection reality gate requires final {label} identity")
    matches = {
        int(row["player_id"])
        for row in rows
        if isinstance(row, dict)
        and row.get("player_id") is not None
        and str(row.get("web_name") or "") == str(name)
    }
    if len(matches) != 1:
        raise SystemExit(
            f"selection reality gate cannot uniquely resolve {label}: "
            f"name={name!r} matches={sorted(matches)}"
        )
    return next(iter(matches))


def _ordered_bench_ids(rec: dict, squad: list[dict]) -> list[int]:
    explicit = rec.get("outfield_bench_order_ids") or []
    if explicit:
        result = [int(pid) for pid in explicit]
    else:
        names = rec.get("outfield_bench_order") or []
        if len(names) != 3:
            raise SystemExit(
                "selection reality gate requires solver-produced three-player outfield bench order"
            )
        result = [_unique_name_id(squad, str(name), "outfield bench") for name in names]
    if len(result) != 3 or len(set(result)) != 3:
        raise SystemExit(
            "selection reality gate requires three unique outfield bench player IDs"
        )
    return result


def _appearance_map(players: pd.DataFrame) -> dict[int, float]:
    values = pd.to_numeric(
        players.get("appearance_probability", pd.Series(1.0, index=players.index)),
        errors="coerce",
    ).fillna(1.0)
    return {
        int(pid): min(max(float(value), 0.0), 1.0)
        for pid, value in zip(players["player_id"].astype(int), values)
    }


def _current_xp_map(projections: pd.DataFrame, gameweek: int) -> dict[int, float]:
    rows = projections[projections["gw"].astype(int).eq(int(gameweek))]
    if "xp" not in rows.columns:
        raise SystemExit("selection reality mechanics parity requires canonical xp")
    values = rows.groupby("player_id")["xp"].sum()
    return {int(pid): float(value) for pid, value in values.items()}


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
        "contract": "apex-selection-reality-v2",
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


def _validate_mechanics_parity(
    *,
    payload: dict,
    rec: dict,
    squad_rows: list[dict],
    xi_ids: set[int],
    bench_ids: list[int],
    decision_players: pd.DataFrame,
    projections: pd.DataFrame,
    current_gameweek: int,
) -> dict:
    selected_ids = _ids_from_rows(squad_rows)
    squad = decision_players[
        decision_players["player_id"].astype(int).isin(selected_ids)
    ].copy()
    captain_eligible = captain_eligible_ids(decision_players)
    xi_eligible = set(
        decision_players.loc[
            decision_players["xi_evidence_eligible"].fillna(False), "player_id"
        ].astype(int)
    )
    exact_xi, mechanics = optimise_fixed_squad_gameweek(
        squad,
        _current_xp_map(projections, current_gameweek),
        _appearance_map(decision_players),
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
        enforce_current_bench_resilience=True,
    )
    exact_xi_ids = set(exact_xi["player_id"].astype(int))
    captain_id = int(
        rec.get("captain_id")
        or _unique_name_id(squad_rows, rec.get("captain"), "captain")
    )
    vice_id = int(
        rec.get("vice_captain_id")
        or _unique_name_id(squad_rows, rec.get("vice_captain"), "vice-captain")
    )
    bench_gk_id = int(
        rec.get("bench_gk_id")
        or _unique_name_id(squad_rows, rec.get("bench_gk"), "bench goalkeeper")
    )
    expected_total = rec.get("gw1_expected_total_with_mechanics")
    mismatches: list[str] = []
    if exact_xi_ids != xi_ids:
        mismatches.append(
            f"XI ids published={sorted(xi_ids)} exact={sorted(exact_xi_ids)}"
        )
    if captain_id != int(mechanics.captain_id):
        mismatches.append(
            f"captain published={captain_id} exact={int(mechanics.captain_id)}"
        )
    if vice_id != int(mechanics.vice_captain_id):
        mismatches.append(
            f"vice published={vice_id} exact={int(mechanics.vice_captain_id)}"
        )
    if bench_gk_id != int(mechanics.bench_gk_id):
        mismatches.append(
            f"bench_gk published={bench_gk_id} exact={int(mechanics.bench_gk_id)}"
        )
    exact_order = [int(pid) for pid in mechanics.outfield_bench_order]
    if bench_ids != exact_order:
        mismatches.append(
            f"outfield_bench_order published={bench_ids} exact={exact_order}"
        )
    if expected_total is None or abs(
        float(expected_total) - float(mechanics.expected_total_points)
    ) > 1e-8:
        mismatches.append(
            "expected total published="
            f"{expected_total!r} exact={float(mechanics.expected_total_points):.12f}"
        )
    if mismatches:
        raise SystemExit(
            "published current-Gameweek mechanics do not reconcile to the sealed exact "
            "mechanics solve: " + "; ".join(mismatches)
        )
    parity = {
        "contract": "apex-published-mechanics-parity-v1",
        "ready": True,
        "current_gameweek": int(current_gameweek),
        "xi_ids": sorted(exact_xi_ids),
        "captain_id": int(mechanics.captain_id),
        "vice_captain_id": int(mechanics.vice_captain_id),
        "bench_gk_id": int(mechanics.bench_gk_id),
        "outfield_bench_order_ids": exact_order,
        "expected_total_points": float(mechanics.expected_total_points),
        "bench_resilience_enforced": True,
    }
    payload.setdefault("internal_diagnostics", {})["published_mechanics_parity"] = parity
    return parity


def _audit_final_selection(*, output_dir: Path, bundle_dir: Path) -> None:
    recommendation_path = output_dir / "apex_recommendation_latest.json"
    if not recommendation_path.exists():
        raise SystemExit("selection reality gate requires canonical recommendation output")
    payload = json.loads(recommendation_path.read_text(encoding="utf-8"))
    if payload.get("ready_to_act") is not True:
        return
    rec = payload.get("recommendation") or {}
    squad_rows = rec.get("squad") or []
    xi_rows = rec.get("xi") or []
    if len(squad_rows) != 15 or len(xi_rows) != 11:
        raise SystemExit("selection reality gate requires exact final 15/XI")

    selected_ids = _ids_from_rows(squad_rows)
    xi_ids = _ids_from_rows(xi_rows)
    if len(selected_ids) != 15 or len(xi_ids) != 11 or not xi_ids.issubset(selected_ids):
        raise SystemExit("selection reality gate requires unique legal final 15/XI identities")
    bench_ids = _ordered_bench_ids(rec, squad_rows)

    bundle = DecisionBundle.load(bundle_dir)
    out = bundle.to_pipeline_output()
    sealed_players = out.players.copy()
    if "player_id" not in sealed_players.columns:
        raise SystemExit("selection reality gate requires player_id on sealed player surface")
    hierarchy = load_current_hierarchy_evidence(
        sealed_players,
        Path("data/manual/squad_hierarchy.csv"),
        strict_identity=True,
    )
    decision_players, _ = evidence_eligibility(sealed_players, out.news_audit)
    players = decision_players[
        decision_players["player_id"].astype(int).isin(selected_ids)
    ].copy()
    sealed_ids = set(players["player_id"].astype(int))
    if sealed_ids != selected_ids or len(players) != 15:
        raise SystemExit(
            "selection reality gate selected IDs do not reconcile to sealed player surface"
        )
    by_id = players.set_index("player_id")
    actual_outfield_bench = {
        int(pid)
        for pid in selected_ids - xi_ids
        if int(pid) in by_id.index and str(by_id.loc[int(pid), "position"]) != "GK"
    }
    if set(bench_ids) != actual_outfield_bench:
        raise SystemExit(
            "published outfield bench order does not contain the exact three selected "
            f"outfield substitutes: order={bench_ids} actual={sorted(actual_outfield_bench)}"
        )

    current_gameweek = int(rec.get("current_gameweek") or (out.gameweeks or [0])[0])
    if not out.gameweeks or current_gameweek != int(out.gameweeks[0]):
        raise SystemExit(
            "published recommendation current Gameweek does not match sealed actionable horizon"
        )
    _validate_mechanics_parity(
        payload=payload,
        rec=rec,
        squad_rows=squad_rows,
        xi_ids=xi_ids,
        bench_ids=bench_ids,
        decision_players=decision_players,
        projections=out.projections,
        current_gameweek=current_gameweek,
    )

    result = audit_selected_squad_reality(
        players,
        selected_ids=selected_ids,
        xi_ids=xi_ids,
        bench_ids=bench_ids,
        specialist_report=_frame_if_present(
            output_dir / "specialist_disagreement.csv"
        ),
        hierarchy_evidence=hierarchy,
        transfer_report=_frame_if_present(output_dir / "transfer_intelligence.csv"),
        require_current_evidence=True,
        first_bench_min_appearance=FIRST_BENCH_MIN_APPEARANCE,
        first_bench_min_expected_minutes=FIRST_BENCH_MIN_EXPECTED_MINUTES,
    )
    payload.setdefault("internal_diagnostics", {})["selection_reality"] = {
        "contract": "apex-selection-reality-v2",
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
