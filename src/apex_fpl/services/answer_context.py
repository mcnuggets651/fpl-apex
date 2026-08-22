from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


ANSWER_CONTRACT = "apex-answer-context-v1"
MAX_OFFICIAL_AGE_HOURS = 12.0
MAX_SOURCE_AGE_HOURS = 12.0
REQUIRED_SOURCES = {
    "official_fpl",
    "fpl_core_playerstats",
    "fixture_model",
    "airsenal",
    "news_feeds",
}
FINAL_SELECTORS = {
    "adaptive_gw1_launch_with_transfer_option_value",
    "receding_horizon_current_team_maximum_ev",
}


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _age_hours(value: Any, now: datetime) -> float | None:
    parsed = _parse_time(value)
    return None if parsed is None else max((now - parsed).total_seconds() / 3600.0, 0.0)


def _selector_reason(selector: str) -> str:
    if selector == "adaptive_gw1_launch_with_transfer_option_value":
        return (
            "Selected by the canonical GW1-first launch policy: exact GW1 expected points "
            "are primary, and future legal transfer option value may only choose among squads "
            "inside the disclosed near-equivalent GW1 point band."
        )
    if selector == "receding_horizon_current_team_maximum_ev":
        return (
            "Selected by the canonical current-team receding-horizon policy using the actual "
            "squad, bank, selling prices and free-transfer state; only the freshly solved next "
            "action is executable."
        )
    return "No canonical final-selector explanation is available."


def selected_player_reasons(canonical: dict[str, Any], pinnacle: dict[str, Any]) -> list[dict]:
    """Explain the actual final selector, never a superseded diagnostic squad.

    In-season strategy records are intentionally compact. Forecast and role fields
    therefore fall back to the sealed final-selected-player dossier built from the
    same DecisionBundle. A missing value in both surfaces remains missing and is
    rejected later by the answer gate.
    """
    recommendation = canonical.get("recommendation") or {}
    selector = str(recommendation.get("selector") or "")
    final_evidence = canonical.get("final_selected_player_evidence") or {}
    dossier_by_player = {
        int(row["player_id"]): row
        for row in final_evidence.get("dossiers") or []
        if isinstance(row, dict) and row.get("player_id") is not None
    }
    reasons: list[dict] = []
    for player in recommendation.get("squad") or []:
        if not isinstance(player, dict):
            continue
        player_id = int(player.get("player_id") or 0)
        dossier = dossier_by_player.get(player_id, {})

        def _forecast(player_key: str, dossier_key: str | None = None) -> Any:
            value = player.get(player_key)
            return value if value is not None else dossier.get(dossier_key or player_key)

        reasons.append(
            {
                "player_id": player_id,
                "web_name": player.get("web_name") or dossier.get("web_name"),
                "horizon_xp": player.get("horizon_xp"),
                "expected_minutes": _forecast("expected_minutes"),
                "start_probability": _forecast("start_probability"),
                "projection_confidence": _forecast("projection_confidence"),
                "tactical_role": _forecast("tactical_role"),
                "role_source": _forecast("tactical_role_source", "role_source"),
                "has_current_decision_evidence": dossier.get(
                    "has_current_decision_evidence"
                ),
                "has_decision_grade_evidence": dossier.get(
                    "has_decision_grade_evidence"
                ),
                "current_evidence_count": dossier.get("current_evidence_count", 0),
                "evidence": dossier.get("evidence") or [],
                # Exact-horizon force/ban regret belongs to the internal static
                # diagnostic and is not causal evidence for adaptive/receding picks.
                "selection_regret": None,
                "alternative": None,
                "selector": selector,
                "reason": _selector_reason(selector),
            }
        )
    return reasons


def _captain_surfaces(canonical: dict[str, Any], pinnacle: dict[str, Any]) -> dict[str, Any]:
    """Label captain decisions by objective so diagnostic disagreement is explicit."""
    recommendation = canonical.get("recommendation") or {}
    mechanics = pinnacle.get("gw1_mechanics") or {}
    deterministic = mechanics.get("unrestricted") or {}
    cvar = ((pinnacle.get("robust_cvar_scenarios") or {}).get("unrestricted") or {})
    parity = pinnacle.get("solver_parity") or {}

    def captain_record(payload: dict[str, Any]) -> dict[str, Any]:
        records = payload.get("captain") or []
        return records[0] if records and isinstance(records[0], dict) else {}

    cvar_captain = captain_record(cvar)
    return {
        "production": {
            "label": "canonical_final_strategy",
            "selector": recommendation.get("selector"),
            "captain": recommendation.get("captain"),
            "captain_id": recommendation.get("captain_id"),
            "authority": True,
            "objective": "final strategy selector with exact current-Gameweek mechanics",
        },
        "deterministic_diagnostic": {
            "label": "static_shortlist_gw1_mechanics",
            "captain_id": deterministic.get("captain_id"),
            "captain": deterministic.get("captain_name"),
            "authority": False,
        },
        "cvar_diagnostic": {
            "label": "lower_tail_robustness",
            "captain_id": cvar_captain.get("player_id"),
            "captain": cvar_captain.get("web_name"),
            "authority": False,
        },
        "independent_parity_diagnostic": {
            "label": str(parity.get("comparison_surface") or "unknown"),
            "captain_id": parity.get("external_captain"),
            "apex_captain_id": parity.get("apex_captain"),
            "authority": False,
        },
        "interpretation": (
            "Only canonical_final_strategy is user-facing. Other captain choices test "
            "robustness or solver agreement and cannot silently replace it."
        ),
    }


def build_answer_context(
    canonical: dict[str, Any],
    pinnacle: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    blockers = [str(value) for value in canonical.get("blockers") or []]
    warnings: list[str] = [
        str(value)
        for value in (
            *((pinnacle.get("pinnacle_gate") or {}).get("warnings") or []),
            *((pinnacle.get("data_quality") or {}).get("warnings") or []),
        )
    ]

    recommendation = canonical.get("recommendation") or {}
    selector = str(recommendation.get("selector") or "")
    if canonical.get("strategy_stage") != "final_validated":
        blockers.append("canonical strategy has not completed final validation")
    if selector not in FINAL_SELECTORS:
        blockers.append("canonical recommendation does not use an allowed final strategy selector")

    canonical_snapshot = canonical.get("official_snapshot") or {}
    pinnacle_snapshot = pinnacle.get("official_snapshot") or {}
    canonical_bundle = canonical.get("decision_bundle_id")
    pinnacle_bundle = pinnacle.get("decision_bundle_id")
    if not canonical_bundle or not pinnacle_bundle:
        blockers.append("canonical or Pinnacle decision bundle identity is missing")
    elif canonical_bundle != pinnacle_bundle:
        blockers.append("canonical and Pinnacle decision bundle identities do not match")
    snapshot_fields = ("bootstrap_sha256", "fixtures_sha256")
    if any(canonical_snapshot.get(key) != pinnacle_snapshot.get(key) for key in snapshot_fields):
        blockers.append("canonical and Pinnacle snapshot hashes do not match")

    official_age = _age_hours(canonical_snapshot.get("retrieved_at"), now)
    if official_age is None:
        blockers.append("official FPL snapshot retrieval time is missing or invalid")
    elif official_age > MAX_OFFICIAL_AGE_HOURS:
        blockers.append(
            f"official FPL snapshot is stale ({official_age:.1f}h > {MAX_OFFICIAL_AGE_HOURS:.1f}h)"
        )

    source_health: list[dict] = []
    for source in pinnacle.get("sources") or []:
        if not isinstance(source, dict):
            continue
        age = _age_hours(source.get("checked_at"), now)
        row = {
            "name": source.get("name"),
            "ok": source.get("ok") is True,
            "configured": source.get("configured") is True,
            "checked_at": source.get("checked_at"),
            "age_hours": age,
            "version": source.get("version"),
        }
        source_health.append(row)
        if row["name"] in REQUIRED_SOURCES and (
            not row["configured"]
            or not row["ok"]
            or age is None
            or age > MAX_SOURCE_AGE_HOURS
        ):
            blockers.append(f"required/configured source is unhealthy or stale: {row['name']}")

    robust = pinnacle.get("robust_cvar_scenarios")
    if not isinstance(robust, dict) or not robust:
        blockers.append("required CVaR diagnostics are missing")
    if not pinnacle.get("selection_regret"):
        blockers.append("required selection-regret diagnostics are missing")
    parity = pinnacle.get("solver_parity")
    if not isinstance(parity, dict) or parity.get("comparison_surface") != "pinnacle_ev":
        blockers.append("required same-surface solver parity is missing or invalid")
    elif any(
        (parity.get("official_snapshot") or {}).get(key) != pinnacle_snapshot.get(key)
        for key in snapshot_fields
    ):
        blockers.append("solver parity and Pinnacle snapshot hashes do not match")

    strategy = pinnacle.get("weekly_strategy") or pinnacle.get("initial_squad_contingencies")
    if not isinstance(strategy, dict):
        blockers.append("strategy/transfer state is missing")

    truth = canonical.get("all_player_truth")
    if not isinstance(truth, dict) or truth.get("ready") is not True:
        blockers.append("all-player truth audit is missing or not ready")
    else:
        for field in (
            "hard_fact_coverage",
            "canonical_projection_pair_coverage",
            "airsenal_projection_pair_coverage",
        ):
            try:
                value = float(truth.get(field))
            except (TypeError, ValueError):
                value = 0.0
            if abs(value - 1.0) > 1e-12:
                blockers.append(f"all-player truth coverage is incomplete: {field}={value:.3f}")
        warnings.extend(str(row) for row in truth.get("warnings") or [])

    final_evidence = canonical.get("final_selected_player_evidence")
    if not isinstance(final_evidence, dict):
        blockers.append("final selected-player evidence dossier artifact is missing")
        evidence_coverage = {}
    else:
        evidence_coverage = final_evidence.get("coverage") or {}
        if final_evidence.get("contract") != "apex-player-evidence-v2":
            blockers.append("final selected-player evidence contract is not v2")
        if len(final_evidence.get("dossiers") or []) != 15:
            blockers.append("final selected-player evidence does not cover the full squad")
        if evidence_coverage.get("ready") is not True:
            blockers.append("final selected-player evidence coverage is not ready")
        if evidence_coverage.get("captain_evidence_eligible") is not True:
            blockers.append("final captain is evidence-ineligible")
        if evidence_coverage.get("selected_xi_ineligible_ids"):
            blockers.append("final XI contains evidence-ineligible players")

    selected = selected_player_reasons(canonical, pinnacle)
    final_squad_ids = {
        int(row["player_id"])
        for row in recommendation.get("squad") or []
        if isinstance(row, dict) and row.get("player_id") is not None
    }
    evidence_ids = {
        int(row["player_id"])
        for row in (final_evidence or {}).get("dossiers") or []
        if isinstance(row, dict) and row.get("player_id") is not None
    }
    if len(final_squad_ids) != 15 or evidence_ids != final_squad_ids:
        blockers.append("final evidence identities do not match the canonical 15")

    for player in selected:
        if player.get("expected_minutes") is None or player.get("start_probability") is None:
            blockers.append(f"selected player lacks expected-minutes forecast: {player['web_name']}")
        if not player.get("role_source"):
            blockers.append(f"selected player lacks role provenance: {player['web_name']}")
    inferred_roles = [
        str(player.get("web_name"))
        for player in selected
        if player.get("role_source") == "statistical_inference"
    ]
    if inferred_roles:
        warnings.append(
            "selected-player roles are statistical forecasts rather than verified overrides: "
            + ", ".join(inferred_roles)
        )

    blockers = list(dict.fromkeys(blockers))
    warnings = list(dict.fromkeys(warnings))
    safe = (
        canonical.get("ready_to_act") is True
        and pinnacle.get("pinnacle_ready") is True
        and not blockers
    )
    if not safe and not blockers:
        blockers.append("canonical or Pinnacle production gate is not green")

    return {
        "contract": ANSWER_CONTRACT,
        "generated_at": now.isoformat(),
        "only_input_for_apex_answers": True,
        "safe_to_act": safe,
        "ready_to_act": safe,
        "blockers": blockers,
        "warnings": warnings,
        "run_age_hours": official_age,
        "decision_bundle_id": canonical_bundle,
        "versions": {
            "canonical_contract": canonical.get("contract"),
            "pinnacle_contract": pinnacle.get("contract"),
            "official_snapshot_id": canonical_snapshot.get("snapshot_id"),
            "bootstrap_sha256": canonical_snapshot.get("bootstrap_sha256"),
            "fixtures_sha256": canonical_snapshot.get("fixtures_sha256"),
            "decision_bundle_id": canonical_bundle,
        },
        "source_health": source_health,
        "diagnostics": {
            "cvar": robust,
            "selection_regret": pinnacle.get("selection_regret"),
            "solver_parity": parity,
            "pinnacle_gate": pinnacle.get("pinnacle_gate"),
            "captain_surfaces": _captain_surfaces(canonical, pinnacle),
            "static_exact_horizon_equivalence": (
                (pinnacle.get("authoritative_decision") or {}).get("equivalence")
            ),
            "static_exact_horizon_is_authoritative": False,
        },
        "all_player_truth": truth,
        "news_role_evidence": {
            "sources": [
                row
                for row in source_health
                if row["name"] in {"news_feeds", "tactical_roles"}
            ],
            "selected_players": selected,
            "coverage": evidence_coverage,
        },
        "production_result": recommendation if safe else None,
        "canonical_strategy": strategy if safe else None,
        "selected_player_reasons": selected,
        "response_sections": (
            "production_result",
            "current_evidence",
            "unresolved_risks",
            "proposed_model_improvement",
        ),
    }


@dataclass(frozen=True)
class AnswerRoute:
    mode: str
    required_artifact: str


def route_question(question: str) -> AnswerRoute:
    text = question.casefold()
    if any(token in text for token in ("project status", "repo status", "github", "pull request")):
        return AnswerRoute("project_status", "github_release_evidence")
    if any(token in text for token in ("improve", "weakness", "what else", "model gap")):
        return AnswerRoute("model_improvement", "validation_gaps")
    if any(token in text for token in ("transfer", "sell", "buy")):
        return AnswerRoute("transfer", "rolling_horizon_strategy")
    if any(token in text for token in (" vs ", " or ", "compare")):
        return AnswerRoute("player_comparison", "same_snapshot_player_dossier")
    if any(token in text for token in ("start", "starter", "minutes", "lineup")):
        return AnswerRoute("player_role", "player_evidence_dossier")
    if any(token in text for token in ("best team", "squad", "starting 15", "apex team")):
        return AnswerRoute("canonical_team", "apex_answer_context")
    return AnswerRoute("unsupported", "explicit_coverage_decision")
