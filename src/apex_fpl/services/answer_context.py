from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


ANSWER_CONTRACT = "apex-answer-context-v1"
MAX_OFFICIAL_AGE_HOURS = 12.0
MAX_SOURCE_AGE_HOURS = 12.0
REQUIRED_DIAGNOSTICS = ("cvar", "selection_regret", "solver_parity")
REQUIRED_SOURCES = {
    "official_fpl",
    "fpl_core_playerstats",
    "fixture_model",
    "airsenal",
    "news_feeds",
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


def _regret_by_player(rows: Any) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            result[int(row["player_id"])] = row
        except (KeyError, TypeError, ValueError):
            continue
    return result


def selected_player_reasons(canonical: dict[str, Any], pinnacle: dict[str, Any]) -> list[dict]:
    recommendation = canonical.get("recommendation") or {}
    regret = _regret_by_player(pinnacle.get("selection_regret"))
    reasons: list[dict] = []
    for player in recommendation.get("squad") or []:
        if not isinstance(player, dict):
            continue
        player_id = int(player.get("player_id") or 0)
        regret_row = regret.get(player_id, {})
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
                "selection_regret": regret_row.get("regret")
                or regret_row.get("objective_regret"),
                "alternative": regret_row.get("best_replacement_name")
                or regret_row.get("alternative_name"),
                "reason": (
                    "Selected by the canonical optimiser on the matched projection surface; "
                    "the fields above are the reproducible evidence, not a conversational override."
                ),
            }
        )
    return reasons


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

    canonical_snapshot = canonical.get("official_snapshot") or {}
    pinnacle_snapshot = pinnacle.get("official_snapshot") or {}
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
            not row["configured"] or not row["ok"] or age is None or age > MAX_SOURCE_AGE_HOURS
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

    selected = selected_player_reasons(canonical, pinnacle)
    for player in selected:
        if player.get("expected_minutes") is None or player.get("start_probability") is None:
            blockers.append(f"selected player lacks expected-minutes evidence: {player['web_name']}")
        if not player.get("role_source"):
            blockers.append(f"selected player lacks role provenance: {player['web_name']}")
    inferred_roles = [
        str(player.get("web_name"))
        for player in selected
        if player.get("role_source") == "statistical_inference"
    ]
    if inferred_roles:
        warnings.append(
            "selected-player roles still rely on statistical inference rather than verified "
            "authoritative overrides: " + ", ".join(inferred_roles)
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
        "blockers": blockers,
        "warnings": warnings,
        "run_age_hours": official_age,
        "versions": {
            "canonical_contract": canonical.get("contract"),
            "pinnacle_contract": pinnacle.get("contract"),
            "official_snapshot_id": canonical_snapshot.get("snapshot_id"),
            "bootstrap_sha256": canonical_snapshot.get("bootstrap_sha256"),
            "fixtures_sha256": canonical_snapshot.get("fixtures_sha256"),
        },
        "source_health": source_health,
        "diagnostics": {
            "cvar": robust,
            "selection_regret": pinnacle.get("selection_regret"),
            "solver_parity": parity,
            "pinnacle_gate": pinnacle.get("pinnacle_gate"),
        },
        "news_role_evidence": {
            "sources": [
                row for row in source_health if row["name"] in {"news_feeds", "tactical_roles"}
            ],
            "selected_players": selected,
        },
        "production_result": canonical.get("recommendation") if safe else None,
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
