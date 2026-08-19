from __future__ import annotations

import json
from pathlib import Path

from apex_fpl.services.joint_initial_path import JointInitialPathResult, JointPathCandidate


CACHE_CONTRACT = "apex-adaptive-launch-production-v2"
BROAD_CERTIFICATION_MARKER = "Mandatory production convergence certification expanded"


def _candidate(payload: dict | None) -> JointPathCandidate | None:
    if not isinstance(payload, dict):
        return None
    return JointPathCandidate(
        source_rank=int(payload["source_rank"]),
        squad_ids=tuple(int(pid) for pid in payload.get("squad_ids") or []),
        squad_names=tuple(str(name) for name in payload.get("squad_names") or []),
        starting_cost=float(payload["starting_cost"]),
        starting_bank=float(payload["starting_bank"]),
        gw1_expected_points=float(payload["gw1_expected_points"]),
        gw1_regret=float(payload["gw1_regret"]),
        within_gw1_band=bool(payload["within_gw1_band"]),
        future_objective=float(payload["future_objective"]),
        total_hit_cost=int(payload.get("total_hit_cost") or 0),
        weeks=tuple(payload.get("weeks") or []),
    )


def load_cached_hardened_launch(
    path: str | Path,
    *,
    decision_bundle_id: str,
) -> JointInitialPathResult | None:
    """Load the exact broader-certified launch already computed by canonical Apex.

    The cache is advisory only. Any missing lineage, contract, promotion gate or
    mandatory-broadening marker causes a clean cache miss so callers can recompute
    from the sealed DecisionBundle. A blocked football-reality decision may still
    supply a valid mathematical launch because reality withholding deliberately keeps
    ``internal_diagnostics`` while setting the user-facing recommendation to null.
    """
    source = Path(path)
    if not source.exists():
        return None
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    diag = (payload.get("internal_diagnostics") or {}).get("joint_initial_path")
    if not isinstance(diag, dict):
        return None
    if diag.get("contract") != CACHE_CONTRACT:
        return None
    if str(diag.get("decision_bundle_id") or "") != str(decision_bundle_id):
        return None
    gate = diag.get("promotion_gate") or {}
    if not (
        gate.get("promotion_candidate") is True
        and gate.get("candidate_pool_stable") is True
        and gate.get("gw1_floor_respected") is True
    ):
        return None
    note = str(diag.get("note") or "")
    if BROAD_CERTIFICATION_MARKER not in note:
        return None

    selected = _candidate(diag.get("selected"))
    if selected is None or not selected.within_gw1_band:
        return None
    baseline = _candidate(diag.get("baseline"))
    candidates = tuple(
        candidate
        for row in (diag.get("candidates") or [])
        if (candidate := _candidate(row)) is not None
    )
    small = diag.get("small_pool_selected_ids")
    full = diag.get("full_pool_selected_ids")
    return JointInitialPathResult(
        status=str(diag.get("status") or ""),
        baseline=baseline,
        selected=selected,
        candidates=candidates,
        best_gw1_points=(
            None if diag.get("best_gw1_points") is None else float(diag["best_gw1_points"])
        ),
        gw1_regret_tolerance=float(diag.get("gw1_regret_tolerance") or 0.0),
        gw1_floor=None if diag.get("gw1_floor") is None else float(diag["gw1_floor"]),
        small_pool_selected_ids=(
            tuple(int(pid) for pid in small) if isinstance(small, list) else None
        ),
        full_pool_selected_ids=(
            tuple(int(pid) for pid in full) if isinstance(full, list) else None
        ),
        candidate_pool_stable=bool(diag.get("candidate_pool_stable")),
        squad_overlap=(
            None if diag.get("squad_overlap") is None else int(diag["squad_overlap"])
        ),
        gw1_delta_vs_static=(
            None
            if diag.get("gw1_delta_vs_static") is None
            else float(diag["gw1_delta_vs_static"])
        ),
        future_delta_vs_static=(
            None
            if diag.get("future_delta_vs_static") is None
            else float(diag["future_delta_vs_static"])
        ),
        projection_col=str(diag.get("projection_col") or "xp"),
        note=note,
    )
