from __future__ import annotations

from typing import Any

import numpy as np


SCIPY_MILP_STATUS = {
    0: "Optimal",
    1: "SolverLimit",
    2: "Infeasible",
    3: "Unbounded",
    4: "SolverError",
}


def finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def scipy_milp_status(result: Any) -> str:
    """Return a non-lossy Apex status for scipy.optimize.milp/HiGHS.

    A feasible incumbent after a limit is still not a proof of optimality. Likewise,
    a timeout is never allowed to masquerade as mathematical infeasibility.
    """
    code_raw = getattr(result, "status", None)
    code = int(code_raw) if code_raw is not None else None
    if (
        bool(getattr(result, "success", False))
        and getattr(result, "x", None) is not None
        and code == 0
    ):
        return "Optimal"
    return SCIPY_MILP_STATUS.get(code, "SolverError")


def scipy_milp_metadata(
    result: Any,
    *,
    relative_gap: float | None = None,
    time_limit: float | None = None,
) -> dict[str, Any]:
    fun = finite_float(getattr(result, "fun", None))
    dual = finite_float(getattr(result, "mip_dual_bound", None))
    gap = finite_float(getattr(result, "mip_gap", None))
    nodes = getattr(result, "mip_node_count", None)
    code_raw = getattr(result, "status", None)
    code = int(code_raw) if code_raw is not None else None
    payload: dict[str, Any] = {
        "success": bool(getattr(result, "success", False)),
        "status": scipy_milp_status(result),
        "status_code": code,
        "termination_reason": str(getattr(result, "message", "unknown")),
        "incumbent": None if fun is None else float(-fun),
        "bound": None if dual is None else float(-dual),
        "relative_gap": gap,
        "node_count": None if nodes is None else int(nodes),
    }
    if relative_gap is not None:
        payload["configured_relative_gap"] = float(relative_gap)
    if time_limit is not None:
        payload["time_limit_seconds"] = float(time_limit)
    return payload


def certified_infeasible(status: str, solver: dict[str, Any] | None) -> bool:
    """True only for an explicit HiGHS mathematical-infeasibility certificate."""
    if status != "Infeasible" or not isinstance(solver, dict):
        return False
    try:
        code = int(solver.get("status_code"))
    except (TypeError, ValueError):
        return False
    return code == 2
