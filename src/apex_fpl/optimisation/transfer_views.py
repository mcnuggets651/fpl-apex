from __future__ import annotations

import pandas as pd

from apex_fpl.optimisation.transfers import TransferPlan, optimise_transfer_plan


def optimise_transfer_plan_view(
    players: pd.DataFrame,
    projections: pd.DataFrame,
    gameweeks: list[int],
    current_squad: set[int],
    *,
    projection_col: str = "xp",
    **kwargs,
) -> TransferPlan:
    """Run the transfer MILP on an explicit projection surface.

    The production transfer optimiser historically consumes the column named
    ``risk_adjusted_xp``. Pinnacle needs a clean separation between maximum expected
    value and risk robustness, so this adapter supplies any named projection column
    to the exact same legal transfer formulation without duplicating the MILP.

    By default Pinnacle uses ensemble mean ``xp``. The legacy/risk-adjusted view can
    still be requested explicitly with ``projection_col='risk_adjusted_xp'``.
    """
    if projection_col not in projections.columns:
        if projection_col == "xp" and "risk_adjusted_xp" in projections.columns:
            projection_col = "risk_adjusted_xp"
        else:
            raise ValueError(f"projection column not found: {projection_col}")
    view = projections.copy()
    view["risk_adjusted_xp"] = pd.to_numeric(
        view[projection_col], errors="coerce"
    ).fillna(0.0)
    return optimise_transfer_plan(
        players,
        view,
        gameweeks,
        current_squad,
        **kwargs,
    )
