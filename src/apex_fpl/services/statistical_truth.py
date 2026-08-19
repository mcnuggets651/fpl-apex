from __future__ import annotations

import numpy as np
import pandas as pd

from apex_fpl.services.player_truth import audit_player_truth


STATISTICAL_TRUTH_CONTRACT = "apex-statistical-truth-v1"


def audit_statistical_truth(
    players: pd.DataFrame,
    projections: pd.DataFrame,
    *,
    expected_players: int | None = None,
) -> dict:
    """Extend all-player truth with finite-value and provenance classification checks."""
    base = audit_player_truth(players, projections, expected_players)
    blockers = list(base.get("blockers") or [])
    warnings = list(base.get("warnings") or [])

    numeric_player_fields = [
        field
        for field in (
            "price",
            "expected_minutes",
            "appearance_probability",
            "start_probability",
            "minutes_confidence",
            "role_confidence",
        )
        if field in players.columns
    ]
    invalid_player_values: dict[str, list[int]] = {}
    for field in numeric_player_fields:
        values = pd.to_numeric(players[field], errors="coerce")
        invalid = values.notna() & ~np.isfinite(values)
        if invalid.any():
            invalid_player_values[field] = (
                players.loc[invalid, "player_id"].astype(int).head(20).tolist()
            )
    if invalid_player_values:
        blockers.append(f"non-finite player statistical fields: {invalid_player_values}")

    projection_col = next(
        (col for col in ("xp", "canonical_ev_xp", "risk_adjusted_xp") if col in projections.columns),
        None,
    )
    if projection_col is None:
        blockers.append("projection surface has no canonical expected-points column")
    else:
        values = pd.to_numeric(projections[projection_col], errors="coerce")
        invalid = values.isna() | ~np.isfinite(values) | (values < 0)
        if invalid.any():
            sample = projections.loc[invalid, ["player_id", "gw", projection_col]].head(20)
            blockers.append(
                "canonical projection contains invalid values: " + str(sample.to_dict("records"))
            )

    role_source = players.get(
        "tactical_role_source",
        pd.Series("unknown", index=players.index, dtype="string"),
    ).fillna("unknown").astype(str)
    role_counts = role_source.value_counts(dropna=False).astype(int).to_dict()
    unknown_roles = int((role_source == "unknown").sum())
    if unknown_roles:
        warnings.append(
            f"{unknown_roles}/{len(players)} players have unknown tactical-role provenance; "
            "unknown remains explicit and is not promoted to a fact"
        )

    minutes_class = {
        str(row.get("minutes_class") or "unknown")
        for row in base.get("players") or []
    }
    return {
        "contract": STATISTICAL_TRUTH_CONTRACT,
        "ready": not blockers,
        "player_count": int(len(players)),
        "expected_official_player_count": expected_players,
        "projection_rows": int(len(projections)),
        "projection_column": projection_col,
        "hard_fact_coverage": base.get("hard_fact_coverage"),
        "canonical_projection_pair_coverage": base.get("canonical_projection_pair_coverage"),
        "airsenal_projection_pair_coverage": base.get("airsenal_projection_pair_coverage"),
        "role_provenance_counts": role_counts,
        "minutes_provenance_classes": sorted(minutes_class),
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "base_player_truth_contract": base.get("contract"),
    }
