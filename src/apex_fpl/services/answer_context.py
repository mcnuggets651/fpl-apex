from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from apex_fpl.services.projection_registry import PROJECTION_PROVIDERS, normalise_provider_key, provider_spec


ANSWER_CONTRACT = "apex-answer-context-v2"
MAX_OFFICIAL_AGE_HOURS = 12.0
MAX_SOURCE_AGE_HOURS = 12.0
BASE_REQUIRED_SOURCES = {"official_fpl"}
OPTIONAL_ENRICHMENT_SOURCES = {
    "fpl_core_playerstats",
    "fixture_model",
    "understat_team_model",
}
EVIDENCE_SOURCES = {"news_feeds", "news_source_health", "tactical_roles"}
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
    """Explain the actual final selector, never a superseded diagnostic squad."""
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
        reasons.append(
            {
                "player_id": player_id,
                "web_name": player.get("web_name"),
                "horizon_xp": player.get("horizon_xp"),
                "expected_minutes": player.get("expected_minutes"),
                "start_probability": player.get("start_probability"),
                "projection_confidence": player.get("projection_confidence"),
                "tactical_role": player.get("tactical_role"),
                "role_source": player.get("tactical_role_source"),
                "has_current_decision_evidence": dossier.get(
                    "has_current_decision_evidence"
                ),
                "has_decision_grade_evidence": dossier.get(
                    "has_decision_grade_evidence"
                ),
                "current_evidence_count": dossier.get("current_evidence_count", 0),
                "evidence": dossier.get("evidence") or [],
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


def _fresh_status(row: dict[str, Any], *, fresh_label: str = "fresh") -> str:
    if not row or not row.get("configured"):
        return "temporarily_unavailable"
    if not row.get("ok"):
        detail = str(row.get("detail") or "").casefold()
        return (
            "schema_invalid"
            if any(token in detail for token in ("schema", "malformed", "empty", "invalid"))
            else "temporarily_unavailable"
        )
    age = row.get("age_hours")
    if age is None or float(age) > MAX_SOURCE_AGE_HOURS:
        return "stale"
    return fresh_label


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

    truth = canonical.get("all_player_truth")
    champion_key = ""
    champion = None
    if not isinstance(truth, dict) or truth.get("ready") is not True:
        blockers.append("all-player truth audit is missing or not ready")
    else:
        try:
            champion_key = normalise_provider_key(str(truth.get("champion_provider") or ""))
            champion = provider_spec(champion_key)
        except ValueError:
            blockers.append("all-player truth does not identify a valid production champion")
        if truth.get("contract") != "apex-player-truth-v2":
            blockers.append("all-player truth contract is not provider-neutral v2")
        for field in (
            "hard_fact_coverage",
            "canonical_projection_pair_coverage",
            "champion_projection_pair_coverage",
        ):
            try:
                value = float(truth.get(field))
            except (TypeError, ValueError):
                value = 0.0
            if abs(value - 1.0) > 1e-12:
                blockers.append(f"all-player truth coverage is incomplete: {field}={value:.3f}")
        warnings.extend(str(row) for row in truth.get("warnings") or [])

    required_sources = set(BASE_REQUIRED_SOURCES)
    if champion is not None:
        required_sources.add(champion.source_status_name)

    provider_source_names = {
        spec.source_status_name for spec in PROJECTION_PROVIDERS.values()
    }
    source_health: list[dict] = []
    for source in pinnacle.get("sources") or []:
        if not isinstance(source, dict):
            continue
        name = str(source.get("name") or "")
        # Forecast freshness is provider-generation freshness, not the later time at
        # which Apex happened to inspect the provider file.
        freshness_at = (
            source.get("generated_at")
            if name in provider_source_names
            else source.get("checked_at")
        )
        age = _age_hours(freshness_at, now)
        row = {
            "name": name,
            "ok": source.get("ok") is True,
            "configured": source.get("configured") is True,
            "checked_at": source.get("checked_at"),
            "generated_at": source.get("generated_at"),
            "freshness_at": freshness_at,
            "age_hours": age,
            "version": source.get("version"),
            "detail": source.get("detail"),
        }
        source_health.append(row)
        if row["name"] in required_sources and (
            not row["configured"]
            or not row["ok"]
            or age is None
            or age > MAX_SOURCE_AGE_HOURS
        ):
            blockers.append(
                f"required/configured source is unhealthy or stale: {row['name']}"
            )
        elif row["name"] in OPTIONAL_ENRICHMENT_SOURCES and (
            not row["configured"]
            or not row["ok"]
            or age is None
            or age > MAX_SOURCE_AGE_HOURS
        ):
            warnings.append(f"optional enrichment is unhealthy or stale: {row['name']}")
        elif row["name"] in EVIDENCE_SOURCES and row["configured"] and not row["ok"]:
            warnings.append(
                f"evidence source is unhealthy; selected-player evidence gate decides materiality: {row['name']}"
            )

    present_sources = {str(row.get("name")) for row in source_health}
    for required_source in sorted(required_sources - present_sources):
        blockers.append(f"required source status is missing: {required_source}")

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
            blockers.append(
                f"selected player lacks expected-minutes forecast: {player['web_name']}"
            )
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

    source_by_name = {str(row.get("name")): row for row in source_health}
    champion_health = (
        source_by_name.get(champion.source_status_name, {}) if champion is not None else {}
    )
    core_health = source_by_name.get("fpl_core_playerstats", {})
    understat_health = source_by_name.get("understat_team_model", {})

    shadow_projection_status: dict[str, Any] = {}
    for key, spec in PROJECTION_PROVIDERS.items():
        if key == champion_key:
            continue
        if key == "apex":
            shadow_projection_status[key] = {
                "provider": spec.display_name,
                "authority": "shadow",
                "status": "available",
            }
            continue
        health = source_by_name.get(spec.source_status_name, {})
        shadow_projection_status[key] = {
            "provider": spec.display_name,
            "authority": "shadow",
            "status": _fresh_status(health),
            "version": health.get("version"),
            "generated_at": health.get("generated_at"),
        }

    champion_display = champion.display_name if champion is not None else None
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
            "champion_provider": champion_key or None,
        },
        "source_health": source_health,
        "authority_chain": [
            "official_fpl:factual_truth",
            f"{champion_key or 'unknown'}:production_statistical_xp",
            "football_enrichment_and_evidence",
            "apex_optimizer:decision_authority",
            "non_champion_providers:shadow",
            "prospective_calibration:promotion_judge",
        ],
        "official_fpl": {
            "authority": "factual_truth",
            "status": (
                "fresh"
                if official_age is not None and official_age <= MAX_OFFICIAL_AGE_HOURS
                else "stale"
            ),
            "snapshot_id": canonical_snapshot.get("snapshot_id"),
            "retrieved_at": canonical_snapshot.get("retrieved_at"),
            "bootstrap_sha256": canonical_snapshot.get("bootstrap_sha256"),
            "fixtures_sha256": canonical_snapshot.get("fixtures_sha256"),
        },
        "canonical_projection": {
            "provider": champion_display,
            "provider_key": champion_key or None,
            "authority": "production",
            "status": _fresh_status(champion_health),
            "generated_at": champion_health.get("generated_at"),
            "checked_at": champion_health.get("checked_at"),
            "age_hours": champion_health.get("age_hours"),
            "version": champion_health.get("version"),
            "fallback_authority": None,
        },
        "enrichment": {
            "understat": {
                "authority": "enrichment_shadow_input",
                "status": _fresh_status(
                    understat_health, fresh_label="fresh_current_season"
                ),
                "version": understat_health.get("version"),
            },
            "fpl_core": {
                "authority": "enrichment",
                "status": _fresh_status(core_health),
                "version": core_health.get("version"),
            },
        },
        "shadow_projections": shadow_projection_status,
        "optimizer": {
            "authority": "decision",
            "status": "optimal" if safe else "blocked",
        },
        "decision": {"status": "actionable" if safe else "blocked"},
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
                if row["name"] in EVIDENCE_SOURCES
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
