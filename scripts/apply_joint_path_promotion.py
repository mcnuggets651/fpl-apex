#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from apex_fpl.optimisation.exact_decision import optimise_fixed_squad_gameweek
from apex_fpl.services.answer_context import build_answer_context
from apex_fpl.services.decision_bundle import DecisionBundle
from apex_fpl.services.decision_eligibility import captain_eligible_ids, evidence_eligibility
from apex_fpl.services.joint_initial_path import optimise_joint_initial_path

TRANSFER_CANDIDATE_LIMIT = 180


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return payload


def _records(frame: pd.DataFrame) -> list[dict]:
    if frame.empty:
        return []
    return json.loads(frame.to_json(orient="records"))


def _launch_gate(result) -> dict:
    selected = result.selected
    floor_respected = bool(selected is not None and selected.within_gw1_band)
    return {
        "gw1_first_optimal": result.status == "optimal",
        "candidate_pool_stable": bool(result.candidate_pool_stable),
        "gw1_floor_respected": floor_respected,
        "promotion_candidate": bool(
            result.status == "optimal"
            and result.candidate_pool_stable
            and floor_respected
        ),
    }


def _render_markdown(payload: dict) -> str:
    rec = payload.get("recommendation") or {}
    if payload.get("ready_to_act") is not True or not rec:
        blockers = payload.get("blockers") or ["strategy policy gate is not ready"]
        return (
            "# Apex Unified Recommendation — NOT READY\n\n"
            + "\n".join(f"- {row}" for row in blockers)
            + "\n"
        )

    def table(rows: list[dict]) -> list[str]:
        lines = ["| Player | Club | Pos | Price | GW xP |", "|:--|:--|:--:|--:|--:|"]
        for row in rows:
            xp = row.get("current_gw_xp", row.get("gw1_xp", row.get("xp", 0.0)))
            lines.append(
                "| {name} | {club} | {pos} | {price:.1f} | {xp:.2f} |".format(
                    name=row.get("web_name", ""),
                    club=row.get("team_name", ""),
                    pos=row.get("position", ""),
                    price=float(row.get("price") or 0.0),
                    xp=float(xp or 0.0),
                )
            )
        return lines

    gameweek = rec.get("current_gameweek") or 1
    lines = [
        "# Apex Unified Recommendation",
        "",
        f"Canonical selector: **{rec.get('selector', '')}**",
        f"Reason: {rec.get('selector_reason', '')}",
        "",
        f"## GW{gameweek}",
        "",
        f"Captain: **{rec.get('captain', '')}**",
        f"Vice-captain: **{rec.get('vice_captain', '')}**",
        f"Expected total with exact mechanics: **{float(rec.get('gw1_expected_total_with_mechanics') or 0.0):.2f}**",
        "",
        "### Starting XI",
        "",
        *table(rec.get("xi") or []),
        "",
        "### Full 15",
        "",
        *table(rec.get("squad") or []),
        "",
        f"Bench GK: **{rec.get('bench_gk', '')}**",
        "Outfield bench: **" + " → ".join(rec.get("outfield_bench_order") or []) + "**",
    ]
    action = rec.get("action_now")
    if isinstance(action, dict):
        ins = ", ".join(str(row.get("web_name")) for row in action.get("transfers_in") or []) or "none"
        outs = ", ".join(str(row.get("web_name")) for row in action.get("transfers_out") or []) or "none"
        lines += [
            "",
            "## Action now",
            "",
            f"- {rec.get('recommended_action', 'none')}",
            f"- Transfers out: {outs}",
            f"- Transfers in: {ins}",
            f"- Hit: -{int(rec.get('recommended_hit') or 0)}",
            f"- Bank after: {float(action.get('bank_after') or 0.0):.1f}",
        ]
    lines += [
        "",
        "Future moves are contingencies only. Refresh projections and re-solve before the next deadline.",
        "",
    ]
    return "\n".join(lines)


def _apply_weekly_strategy(payload: dict, pinnacle: dict) -> None:
    strategy = pinnacle.get("weekly_strategy")
    if not isinstance(strategy, dict):
        raise SystemExit("published personal squad exists but weekly strategy is missing")
    if strategy.get("status") != "optimal" or strategy.get("state_transition_reconciled") is not True:
        raise SystemExit("weekly strategy is not optimal or its team-state transition does not reconcile")
    squad = strategy.get("canonical_squad") or []
    xi = strategy.get("canonical_xi") or []
    if len(squad) != 15 or len(xi) != 11:
        raise SystemExit("weekly strategy does not expose an exact legal 15/XI")
    if not strategy.get("canonical_captain") or not strategy.get("canonical_vice_captain"):
        raise SystemExit("weekly strategy exact captain/vice is missing")

    policy = payload.setdefault("decision_policy", {})
    policy.update(
        {
            "primary_selection": (
                "receding-horizon maximum-EV policy from the actual current FPL squad; "
                "execute only the newly solved first action"
            ),
            "adaptive_launch_active": False,
            "weekly_receding_horizon_is_canonical": True,
            "future_transfer_rules": (
                "rolled free transfers, current cash/selling prices and explicit -4 hit costs; "
                "stored later moves are never executable without a fresh projection solve"
            ),
        }
    )
    payload["recommendation"] = {
        "selector": "receding_horizon_current_team_maximum_ev",
        "selector_reason": (
            "Apex starts from the manager's real permanent squad and current bank/free-transfer "
            "state, re-solves on the latest projection surface, exact-rescores the resulting "
            "current Gameweek squad, and publishes only that first action."
        ),
        "objective": strategy.get("optimal_objective"),
        "objective_reconciliation": strategy.get("optimal_objective"),
        "current_gameweek": strategy.get("next_gw"),
        "squad": squad,
        "xi": xi,
        "captain": strategy.get("canonical_captain"),
        "vice_captain": strategy.get("canonical_vice_captain"),
        "bench_gk": strategy.get("canonical_bench_gk"),
        "outfield_bench_order": strategy.get("canonical_outfield_bench_order") or [],
        "gw1_expected_total_with_mechanics": strategy.get("canonical_expected_points"),
        "recommended_action": strategy.get("recommended_action"),
        "recommended_transfers": strategy.get("recommended_transfers"),
        "recommended_hit": strategy.get("recommended_hit"),
        "roll_regret": strategy.get("roll_regret"),
        "action_now": strategy.get("action_now"),
        "planned_transfer_path": strategy.get("contingent_future") or [],
        "future_moves_are_contingent": True,
        "state_transition_reconciled": True,
    }
    payload.setdefault("internal_diagnostics", {})["canonical_weekly_strategy"] = strategy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", default="data/generated/decision_bundle")
    parser.add_argument("--output-dir", default="data/generated")
    args = parser.parse_args()

    bundle = DecisionBundle.load(args.bundle_dir)
    out = bundle.to_pipeline_output()
    output_dir = Path(args.output_dir)
    recommendation_path = output_dir / "apex_recommendation_latest.json"
    context_path = output_dir / "apex_answer_context.json"
    markdown_path = output_dir / "apex_recommendation_latest.md"
    pinnacle_path = output_dir / "pinnacle_latest.json"

    payload = _load(recommendation_path)
    pinnacle = _load(pinnacle_path)
    if payload.get("ready_to_act") is not True:
        raise SystemExit("strategy policy requires an already-actionable canonical base packet")
    if payload.get("decision_bundle_id") != bundle.bundle_id:
        raise SystemExit("canonical recommendation does not match the sealed decision bundle")
    if pinnacle.get("decision_bundle_id") != bundle.bundle_id:
        raise SystemExit("Pinnacle diagnostic does not match the sealed decision bundle")

    personal = pinnacle.get("personal_team") or {}
    personal_state = personal.get("team_state") if isinstance(personal, dict) else None
    published_personal_squad = bool(
        isinstance(personal_state, dict) and personal_state.get("published_gw")
    )

    if published_personal_squad:
        _apply_weekly_strategy(payload, pinnacle)
    else:
        if not out.gameweeks or int(out.gameweeks[0]) != 1:
            raise SystemExit("no published personal squad exists outside the pre-GW1 launch state")
        players, eligibility = evidence_eligibility(out.players, out.news_audit)
        captain_eligible = captain_eligible_ids(players)
        xi_eligible = set(
            players.loc[players["xi_evidence_eligible"], "player_id"].astype(int)
        )
        settings = bundle.settings
        tolerance = float(settings.get("exact_near_equivalent_points", 0.25))
        result = optimise_joint_initial_path(
            players,
            out.projections,
            out.gameweeks,
            budget=float(settings["budget"]),
            max_per_team=int(settings["max_per_team"]),
            decay=float(settings["fixture_decay"]),
            projection_col="xp",
            captain_eligible=captain_eligible,
            xi_eligible=xi_eligible,
            transfer_candidate_limit=TRANSFER_CANDIDATE_LIMIT,
            exact_candidate_limit=int(settings.get("exact_candidate_limit", 16)),
            gw1_regret_tolerance=tolerance,
        )
        gate = _launch_gate(result)
        diagnostics = payload.setdefault("internal_diagnostics", {})
        diagnostics["joint_initial_path"] = {
            "contract": "apex-adaptive-launch-production-v2",
            "decision_bundle_id": bundle.bundle_id,
            "transfer_candidate_limit": TRANSFER_CANDIDATE_LIMIT,
            "eligibility_contract": eligibility,
            "promotion_gate": gate,
            **result.to_dict(),
        }
        if not gate["promotion_candidate"] or result.selected is None:
            payload["ready_to_act"] = False
            payload["blockers"] = list(
                dict.fromkeys([
                    *(payload.get("blockers") or []),
                    "adaptive GW1 launch policy failed its stability/GW1-floor gate",
                ])
            )
            payload["recommendation"] = None
        else:
            selected = result.selected
            selected_ids = set(int(pid) for pid in selected.squad_ids)
            squad = players[players["player_id"].astype(int).isin(selected_ids)].copy()
            gw1 = int(out.gameweeks[0])
            px = (
                out.projections[out.projections["gw"].astype(int).eq(gw1)]
                .groupby("player_id")["xp"]
                .sum()
            )
            squad["gw1_xp"] = squad["player_id"].map(px).fillna(0.0)
            appearances = pd.to_numeric(
                players.get("appearance_probability", pd.Series(1.0, index=players.index)),
                errors="coerce",
            ).fillna(1.0)
            appearance = {
                int(pid): min(max(float(prob), 0.0), 1.0)
                for pid, prob in zip(players["player_id"].astype(int), appearances)
            }
            xp_map = {int(pid): float(value) for pid, value in px.items()}
            xi, mechanics = optimise_fixed_squad_gameweek(
                squad,
                xp_map,
                appearance,
                captain_eligible=captain_eligible,
                xi_eligible=xi_eligible,
            )
            names = {
                int(row.player_id): str(row.web_name)
                for row in players[["player_id", "web_name"]]
                .drop_duplicates("player_id")
                .itertuples(index=False)
            }
            payload["recommendation"] = {
                "selector": "adaptive_gw1_launch_with_transfer_option_value",
                "selector_reason": (
                    "Exact GW1 expected points are the primary launch objective. Apex permits "
                    "only the existing near-equivalent GW1 point tolerance, then uses the legal "
                    "future transfer path to choose the most useful bank/FT structure."
                ),
                "objective": float(selected.gw1_expected_points),
                "objective_reconciliation": float(selected.gw1_expected_points),
                "current_gameweek": gw1,
                "best_gw1_expected_points": result.best_gw1_points,
                "gw1_regret_vs_max": selected.gw1_regret,
                "gw1_regret_tolerance": result.gw1_regret_tolerance,
                "future_transfer_option_objective": selected.future_objective,
                "starting_bank": selected.starting_bank,
                "static_horizon_gw1_expected_points": (
                    result.baseline.gw1_expected_points if result.baseline else None
                ),
                "squad": _records(squad.sort_values(["position", "price", "player_id"])),
                "xi": _records(xi.sort_values(["position", "price", "player_id"])),
                "captain": names.get(int(mechanics.captain_id), str(mechanics.captain_id)),
                "vice_captain": names.get(
                    int(mechanics.vice_captain_id), str(mechanics.vice_captain_id)
                ),
                "bench_gk": names.get(int(mechanics.bench_gk_id), str(mechanics.bench_gk_id)),
                "outfield_bench_order": [
                    names.get(int(pid), str(pid)) for pid in mechanics.outfield_bench_order
                ],
                "gw1_expected_total_with_mechanics": float(mechanics.expected_total_points),
                "planned_transfer_path": list(selected.weeks),
                "planned_transfer_hit_cost": int(selected.total_hit_cost),
                "future_moves_are_contingent": True,
            }
            policy = payload.setdefault("decision_policy", {})
            policy.update(
                {
                    "primary_selection": (
                        "GW1 exact expected points first; future transfer option value only among "
                        "launch squads inside the disclosed near-equivalent GW1 point band"
                    ),
                    "adaptive_launch_active": True,
                    "weekly_receding_horizon_is_canonical": True,
                    "starting_squad_transfer_horizon": [int(gw) for gw in out.gameweeks],
                    "future_transfer_rules": (
                        "rolled free transfers, current cash/selling prices and explicit -4 hit costs; "
                        "future moves remain contingent and are re-solved before every deadline"
                    ),
                    "future_price_assumption": (
                        "current official prices held fixed; no speculative price-rise forecast"
                    ),
                }
            )

    answer_context = build_answer_context(payload, pinnacle)
    if answer_context.get("safe_to_act") is not True:
        payload["ready_to_act"] = False
        payload["blockers"] = list(
            dict.fromkeys([*(payload.get("blockers") or []), *(answer_context.get("blockers") or [])])
        )
        payload["recommendation"] = None
        answer_context = build_answer_context(payload, pinnacle)

    recommendation_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    context_path.write_text(json.dumps(answer_context, indent=2), encoding="utf-8")
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")

    if payload.get("ready_to_act") is not True or answer_context.get("safe_to_act") is not True:
        raise SystemExit("adaptive strategy policy failed the canonical answer gate")

    print(
        json.dumps(
            {
                "selector": payload["recommendation"]["selector"],
                "current_gameweek": payload["recommendation"].get("current_gameweek"),
                "recommended_action": payload["recommendation"].get("recommended_action"),
                "gw1_regret_vs_max": payload["recommendation"].get("gw1_regret_vs_max"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
