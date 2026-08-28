from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apex_fpl.services.decision_eligibility import (
    MIN_CAPTAIN_APPEARANCE_PROBABILITY,
    MIN_CAPTAIN_EXPECTED_MINUTES,
    MIN_CAPTAIN_START_PROBABILITY,
)


REQUIRED_SCENARIOS = ("unrestricted", "haaland", "no-haaland")
# The sealed base Apex safety gate already validates Official FPL + the configured
# forecast champion. Pinnacle must not reintroduce stale provider/Core/news coupling.
REQUIRED_SOURCES = ("official_fpl",)

MIN_PUBLISHED_CAPTAIN_FREQUENCY = 0.50
MIN_ROBUST_SQUAD_OVERLAP = 12
MIN_ROBUST_XI_OVERLAP = 9


@dataclass(frozen=True)
class PinnacleReadiness:
    ready: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "ready": self.ready,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
        }


def _check_solution(container: dict[str, Any], name: str, label: str, blockers: list[str]) -> None:
    row = container.get(name)
    if not isinstance(row, dict):
        blockers.append(f"{label} scenario missing: {name}")
        return
    if row.get("status") != "Optimal":
        blockers.append(f"{label} scenario not Optimal: {name}")
    if len(row.get("squad") or []) != 15:
        blockers.append(f"{label} {name} does not contain a 15-player squad")
    if len(row.get("xi") or []) != 11:
        blockers.append(f"{label} {name} does not contain an 11-player XI")


def _number(row: dict[str, Any], field: str) -> float | None:
    try:
        value = float(row.get(field))
    except (TypeError, ValueError):
        return None
    return value


def _check_captain_evidence(
    deterministic: dict[str, Any],
    mechanics: dict[str, Any],
    name: str,
    blockers: list[str],
) -> None:
    mechanic = mechanics.get(name)
    solution = deterministic.get(name)
    if not isinstance(mechanic, dict) or not isinstance(solution, dict):
        return
    try:
        captain_id = int(mechanic["captain_id"])
    except (KeyError, TypeError, ValueError):
        blockers.append(f"captain identity missing: {name}")
        return
    candidates = [
        row
        for row in solution.get("squad") or []
        if isinstance(row, dict) and str(row.get("player_id")) == str(captain_id)
    ]
    if len(candidates) != 1:
        blockers.append(f"captain evidence row missing/ambiguous: {name} player_id={captain_id}")
        return
    row = candidates[0]
    name_label = str(row.get("web_name") or captain_id)
    # Projection confidence is not a hard captain field unless the production provider
    # exposes a calibrated confidence contract. Minutes/participation evidence remains
    # mandatory and selected-player evidence is validated separately below.
    floors = (
        ("expected_minutes", MIN_CAPTAIN_EXPECTED_MINUTES, "expected minutes"),
        ("start_probability", MIN_CAPTAIN_START_PROBABILITY, "start probability"),
        (
            "appearance_probability",
            MIN_CAPTAIN_APPEARANCE_PROBABILITY,
            "appearance probability",
        ),
    )
    for field, minimum, label in floors:
        value = _number(row, field)
        if value is None:
            blockers.append(f"captain {name_label} missing {label}: {name}")
        elif value < minimum:
            blockers.append(
                f"captain {name_label} {label} {value:.1%} below production floor "
                f"{minimum:.1%}: {name}"
                if "probability" in field
                else f"captain {name_label} {label} {value:.1f} below production floor "
                f"{minimum:.1f}: {name}"
            )


def evaluate_pinnacle_payload(payload: dict[str, Any]) -> PinnacleReadiness:
    blockers: list[str] = []
    warnings: list[str] = []

    if payload.get("safe_to_act") is not True:
        blockers.append("base Apex safe_to_act is not true")
    if payload.get("full_apex_ready") is not True:
        blockers.append("base Apex full_apex_ready is not true")

    quality = payload.get("data_quality")
    if not isinstance(quality, dict):
        blockers.append("field-level data-quality report is missing")
    elif quality.get("ready") is not True:
        blockers.append("field-level data-quality gate is not ready")

    source_rows = payload.get("sources") or []
    sources = {str(row.get("name")): row for row in source_rows if isinstance(row, dict)}
    for name in REQUIRED_SOURCES:
        row = sources.get(name)
        if row is None:
            blockers.append(f"required source absent: {name}")
        elif row.get("ok") is not True or row.get("configured") is not True:
            blockers.append(f"required source not healthy/configured: {name}")

    gameweeks = payload.get("gameweeks") or []
    if gameweeks and int(gameweeks[0]) == 1:
        previous = sources.get("fpl_core_previous_season")
        if previous is None:
            blockers.append("pre-GW1 prior-season evidence source is absent")
        elif previous.get("ok") is not True or previous.get("configured") is not True:
            blockers.append("pre-GW1 prior-season evidence source is not healthy/configured")

    snapshot = payload.get("official_snapshot") or {}
    for field in ("snapshot_id", "retrieved_at", "bootstrap_sha256", "fixtures_sha256"):
        if not snapshot.get(field):
            blockers.append(f"official snapshot missing {field}")

    decision = payload.get("decision_layer") or {}
    if decision.get("stochastic_covariance_layer") is not True:
        blockers.append("correlated stochastic layer is not active")
    if int(decision.get("stochastic_scenarios", 0) or 0) < 128:
        blockers.append("fewer than 128 stochastic projection scenarios")
    if decision.get("exact_gw_mechanics") is not True:
        blockers.append("exact captain/vice/autosub mechanics are not active")
    if decision.get("authoritative_exact_horizon_mechanics") is not True:
        blockers.append("authoritative exact mechanics are not active across the horizon")
    if decision.get("captain_eligibility_enforced_in_all_solves") is not True:
        blockers.append("captain/vice evidence floors are not enforced in every solve")
    if decision.get("receding_horizon_transfers") is not True:
        blockers.append("receding-horizon transfer policy is not active")
    if decision.get("empirical_decision_frequency") is not True:
        blockers.append("empirical decision-frequency audit is not active")
    if int(decision.get("decision_frequency_solves", 0) or 0) < 16:
        blockers.append("fewer than 16 optimal decision-frequency solves")

    deterministic = payload.get("deterministic_scenarios") or {}
    robust = payload.get("robust_cvar_scenarios") or {}
    for name in REQUIRED_SCENARIOS:
        _check_solution(deterministic, name, "deterministic", blockers)
        _check_solution(robust, name, "robust", blockers)

    mechanics = payload.get("gw1_mechanics") or {}
    for name in REQUIRED_SCENARIOS:
        row = mechanics.get(name)
        if not isinstance(row, dict):
            blockers.append(f"exact GW mechanics missing: {name}")
            continue
        if row.get("captain_id") == row.get("vice_captain_id"):
            blockers.append(f"captain and vice are identical: {name}")
        if len(row.get("outfield_bench_order") or []) != 3:
            blockers.append(f"outfield bench order invalid: {name}")
        _check_captain_evidence(deterministic, mechanics, name, blockers)

    authority = payload.get("authoritative_decision")
    if not isinstance(authority, dict) or authority.get("status") != "Optimal":
        blockers.append("authoritative exact-horizon decision is missing or not optimal")
        authority = {}
    authoritative_solution = authority.get("solution")
    if isinstance(authoritative_solution, dict):
        _check_solution(
            {"authoritative": authoritative_solution},
            "authoritative",
            "exact-horizon",
            blockers,
        )
    else:
        blockers.append("authoritative exact-horizon solution is missing")
        authoritative_solution = {}
    authoritative_weeks = authority.get("weeks") or []
    if len(authoritative_weeks) != len(gameweeks):
        blockers.append("authoritative decision does not cover every horizon Gameweek")
    for row in authoritative_weeks:
        if not isinstance(row, dict):
            blockers.append("authoritative Gameweek mechanics row is invalid")
            continue
        if row.get("captain_id") == row.get("vice_captain_id"):
            blockers.append("authoritative captain and vice are identical")
        if len(row.get("xi_ids") or []) != 11:
            blockers.append("authoritative Gameweek XI does not contain 11 players")
        if len(row.get("outfield_bench_order") or []) != 3:
            blockers.append("authoritative Gameweek bench order is invalid")
    if authoritative_weeks and isinstance(authoritative_solution, dict):
        _check_captain_evidence(
            {"authoritative": authoritative_solution},
            {"authoritative": authoritative_weeks[0]},
            "authoritative",
            blockers,
        )

    evidence = payload.get("selected_player_evidence")
    if not isinstance(evidence, dict):
        blockers.append("selected-player evidence dossiers are missing")
    else:
        dossiers = evidence.get("dossiers") or []
        coverage = evidence.get("coverage") or {}
        if len(dossiers) != 15:
            blockers.append("selected-player evidence dossiers do not cover the full squad")
        if evidence.get("contract") != "apex-player-evidence-v2":
            blockers.append("selected-player evidence contract is not v2")
        if coverage.get("captain_evidence_eligible") is not True:
            blockers.append("published captain is evidence-ineligible")
        selected_ineligible = coverage.get("selected_xi_ineligible_ids") or []
        if selected_ineligible:
            blockers.append(
                "published XI contains evidence-ineligible players: "
                + ", ".join(str(pid) for pid in selected_ineligible)
            )
        if coverage.get("ready") is not True:
            blockers.append("selected-player evidence coverage gate is not ready")
    source_health = payload.get("evidence_source_health") or {}
    if source_health.get("ready") is not True:
        blockers.append("numerical evidence source-health gate is not ready")
    eligibility = payload.get("evidence_eligibility") or {}
    if eligibility.get("contract") != "apex-evidence-eligibility-v2":
        blockers.append("pre-solve evidence-eligibility report is missing")
    objective = _number(authority, "objective")
    reconciled = _number(authority, "objective_reconciliation")
    if objective is None or reconciled is None or abs(objective - reconciled) > 1e-6:
        blockers.append("authoritative exact-horizon objective does not reconcile")
    shortlist = authority.get("shortlist") or {}
    if int(shortlist.get("candidate_count", 0) or 0) < 1:
        blockers.append("authoritative exact-mechanics shortlist is empty")
    elif shortlist.get("complete_within_configured_band") is not True:
        warnings.append(
            "exact-mechanics shortlist hit its configured candidate limit before "
            "exhausting the disclosed near-optimal band"
        )
    equivalence = authority.get("equivalence") or {}
    if equivalence.get("unique_optimum_proven") is not False:
        blockers.append("authoritative decision must not claim an unproven unique optimum")

    regret = payload.get("selection_regret") or []
    if not regret:
        blockers.append("selection-regret stress test is empty")

    frequencies = payload.get("decision_frequencies") or []
    if not frequencies:
        blockers.append("decision-frequency audit is empty")
    else:
        chosen_captain = (
            authoritative_weeks[0].get("captain_id")
            if authoritative_weeks and isinstance(authoritative_weeks[0], dict)
            else None
        )
        captain_row = next(
            (
                row
                for row in frequencies
                if isinstance(row, dict) and str(row.get("player_id")) == str(chosen_captain)
            ),
            None,
        )
        if captain_row is None:
            blockers.append("published unrestricted captain absent from decision frequencies")
        else:
            captain_frequency = _number(captain_row, "captain_frequency")
            xi_frequency = _number(captain_row, "xi_frequency")
            if captain_frequency is None or xi_frequency is None:
                blockers.append("published captain conditional stability evidence is missing")
            elif xi_frequency <= 0:
                blockers.append("published captain never appears in XI across uncertainty re-solves")
            else:
                conditional_frequency = min(captain_frequency / xi_frequency, 1.0)
                if conditional_frequency < MIN_PUBLISHED_CAPTAIN_FREQUENCY:
                    warnings.append(
                        f"published captain is chosen in only {conditional_frequency:.0%} of "
                        "uncertainty re-solves where he remains in the XI; the provisional "
                        f"diagnostic reference is {MIN_PUBLISHED_CAPTAIN_FREQUENCY:.0%}"
                    )

    robust_compare = payload.get("robustness_comparison") or {}
    unrestricted = robust_compare.get("unrestricted") or {}
    overlap = unrestricted.get("squad_overlap")
    if overlap is None:
        blockers.append("deterministic/CVaR unrestricted squad comparison is missing")
    elif int(overlap) < MIN_ROBUST_SQUAD_OVERLAP:
        blockers.append(
            f"deterministic/CVaR unrestricted squads overlap only {overlap}/15; "
            f"production floor is {MIN_ROBUST_SQUAD_OVERLAP}/15"
        )
    xi_overlap = unrestricted.get("xi_overlap")
    if xi_overlap is None:
        blockers.append("deterministic/CVaR unrestricted XI comparison is missing")
    elif int(xi_overlap) < MIN_ROBUST_XI_OVERLAP:
        blockers.append(
            f"deterministic/CVaR unrestricted XIs overlap only {xi_overlap}/11; "
            f"production floor is {MIN_ROBUST_XI_OVERLAP}/11"
        )
    if unrestricted.get("captain_agrees") is not True:
        warnings.append("deterministic/CVaR unrestricted captains disagree")

    decision_calibrated = decision.get("covariance_coefficients_walk_forward_calibrated")
    if decision_calibrated is not True:
        warnings.append(
            "covariance coefficients are transparent priors until enough 2026/27 deadline outcomes exist"
        )

    personal = payload.get("personal_team") or {}
    state = personal.get("team_state") if isinstance(personal, dict) else None
    if isinstance(state, dict) and state.get("published_gw"):
        if not isinstance(payload.get("weekly_strategy"), dict):
            blockers.append("published personal squad exists but weekly strategy is missing")
        if not isinstance(payload.get("chip_window"), dict):
            blockers.append("published personal squad exists but chip-window analysis is missing")
    elif (payload.get("gameweeks") or [None])[0] == 1:
        route = payload.get("initial_squad_contingencies")
        if not isinstance(route, dict):
            blockers.append("pre-GW1 decision is missing its GW2-GW5 contingency route")
        elif route.get("status") not in {"Optimal", "not_applicable"}:
            blockers.append("pre-GW1 GW2-GW5 contingency route is not optimal")
        chips = payload.get("initial_chip_policy")
        if not isinstance(chips, dict) or chips.get("status") != "hold":
            blockers.append("pre-GW1 conservative chip policy is missing")

    parity = payload.get("solver_parity")
    if not isinstance(parity, dict):
        blockers.append("required independent solver parity snapshot is not embedded")
    elif parity.get("comparison_surface") != "pinnacle_ev":
        blockers.append("independent solver parity was not computed on Pinnacle EV")
    else:
        bundle_id = payload.get("decision_bundle_id")
        if bundle_id and parity.get("decision_bundle_id") != bundle_id:
            blockers.append("independent solver parity decision bundle does not match Pinnacle")
        parity_snapshot = parity.get("official_snapshot") or {}
        for field in ("bootstrap_sha256", "fixtures_sha256"):
            if parity_snapshot.get(field) != snapshot.get(field):
                blockers.append(f"independent solver parity {field} does not match Pinnacle")
        if int(parity.get("squad_overlap", 0) or 0) < MIN_ROBUST_SQUAD_OVERLAP:
            blockers.append("independent solver squad parity is below 12/15")
        if int(parity.get("xi_overlap", 0) or 0) < MIN_ROBUST_XI_OVERLAP:
            blockers.append("independent solver XI parity is below 9/11")
        if parity.get("captain_agrees") is not True:
            warnings.append("independent solver selected a different maximum-EV captain")

    return PinnacleReadiness(
        ready=not blockers,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
    )
