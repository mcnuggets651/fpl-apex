from __future__ import annotations

from dataclasses import dataclass
from typing import Any


REQUIRED_SCENARIOS = ("unrestricted", "haaland", "no-haaland")
REQUIRED_SOURCES = ("official_fpl", "fpl_core_playerstats", "airsenal", "news_feeds")


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


def evaluate_pinnacle_payload(payload: dict[str, Any]) -> PinnacleReadiness:
    blockers: list[str] = []
    warnings: list[str] = []

    if payload.get("safe_to_act") is not True:
        blockers.append("base Apex safe_to_act is not true")
    if payload.get("full_apex_ready") is not True:
        blockers.append("base Apex full_apex_ready is not true")

    source_rows = payload.get("sources") or []
    sources = {str(row.get("name")): row for row in source_rows if isinstance(row, dict)}
    for name in REQUIRED_SOURCES:
        row = sources.get(name)
        if row is None:
            blockers.append(f"required source absent: {name}")
        elif row.get("ok") is not True or row.get("configured") is not True:
            blockers.append(f"required source not healthy/configured: {name}")

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
    if decision.get("receding_horizon_transfers") is not True:
        blockers.append("receding-horizon transfer policy is not active")

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

    regret = payload.get("selection_regret") or []
    if not regret:
        blockers.append("selection-regret stress test is empty")

    robust_compare = payload.get("robustness_comparison") or {}
    unrestricted = robust_compare.get("unrestricted") or {}
    overlap = unrestricted.get("squad_overlap")
    if overlap is not None and int(overlap) < 12:
        warnings.append(
            f"deterministic/CVaR unrestricted squads overlap only {overlap}/15; decision is structurally sensitive"
        )

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

    parity = payload.get("solver_parity")
    if parity is None:
        warnings.append("independent solver parity snapshot is not embedded in this run")

    return PinnacleReadiness(
        ready=not blockers,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
    )
