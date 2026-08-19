from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from apex_fpl.services.enrichment import LOW_SAMPLE_ATTACK_MINUTES
from apex_fpl.services.player_truth import audit_player_truth


STATISTICAL_TRUTH_CONTRACT = "apex-statistical-truth-v1"


def _number(row: pd.Series, field: str, default: float = 0.0) -> float:
    value = pd.to_numeric(pd.Series([row.get(field)]), errors="coerce").iloc[0]
    return default if pd.isna(value) else float(value)


def _historical_sample_class(row: pd.Series) -> str:
    minutes = _number(row, "previous_minutes", 0.0)
    if minutes <= 0:
        return "zero_prior_minutes"
    if minutes < float(LOW_SAMPLE_ATTACK_MINUTES):
        return "low_sample_prior"
    return "established_prior"


def _preseason_sample_class(row: pd.Series) -> str:
    appearances = int(max(round(_number(row, "preseason_appearances", 0.0)), 0))
    if appearances <= 0:
        return "no_preseason_sample"
    if appearances == 1:
        return "single_preseason_appearance"
    if appearances == 2:
        return "two_preseason_appearances"
    return "repeated_preseason_sample"


def _availability_state(row: pd.Series, as_of: pd.Timestamp | None) -> tuple[str, str | None]:
    multiplier = row.get("availability_multiplier")
    if multiplier is None or pd.isna(multiplier):
        return "none", None
    expires_raw = row.get("availability_expires_at")
    expires = pd.to_datetime(expires_raw, utc=True, errors="coerce")
    if pd.isna(expires):
        return "missing_expiry", "material manual availability evidence lacks valid expiry"
    if as_of is not None and as_of > expires:
        return "expired", f"manual availability evidence expired at {expires.isoformat()}"
    return "fresh", None


def audit_statistical_truth(
    players: pd.DataFrame,
    projections: pd.DataFrame,
    *,
    expected_players: int | None = None,
    as_of: str | pd.Timestamp | None = None,
) -> dict:
    """Audit all-player statistical validity, sample strength and provenance depth.

    Sample scarcity is reported rather than treated as a factual-data failure: promoted
    players and new signings can legitimately have no prior Premier League sample. A
    row fails only when the statistical surface is invalid or when material governed
    evidence is missing required freshness/provenance state.
    """
    base = audit_player_truth(players, projections, expected_players)
    blockers = list(base.get("blockers") or [])
    warnings = list(base.get("warnings") or [])

    as_of_ts: pd.Timestamp | None = None
    if as_of is not None:
        parsed = pd.to_datetime(as_of, utc=True, errors="coerce")
        if pd.isna(parsed):
            blockers.append(f"statistical truth received invalid as_of timestamp: {as_of!r}")
        else:
            as_of_ts = parsed

    numeric_player_fields = [
        field
        for field in (
            "price",
            "expected_minutes",
            "appearance_probability",
            "start_probability",
            "minutes_confidence",
            "role_confidence",
            "previous_minutes",
            "previous_starts",
            "previous_appearances",
            "previous_role_games",
            "preseason_minutes",
            "preseason_starts",
            "preseason_appearances",
            "preseason_recency_evidence",
            "xg90_context_reliability",
            "xa90_context_reliability",
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
    base_by_id = {
        int(row["player_id"]): row
        for row in base.get("players") or []
        if row.get("player_id") is not None
    }

    evidence_rows: list[dict] = []
    history_counts: Counter[str] = Counter()
    preseason_counts: Counter[str] = Counter()
    availability_counts: Counter[str] = Counter()
    adjusted_ids: list[int] = []
    weak_history_ids: list[int] = []
    no_preseason_ids: list[int] = []

    for _, row in players.iterrows():
        player_id = int(row["player_id"])
        history_class = _historical_sample_class(row)
        preseason_class = _preseason_sample_class(row)
        availability_state, availability_blocker = _availability_state(row, as_of_ts)
        history_counts[history_class] += 1
        preseason_counts[preseason_class] += 1
        availability_counts[availability_state] += 1
        if history_class != "established_prior":
            weak_history_ids.append(player_id)
        if preseason_class == "no_preseason_sample":
            no_preseason_ids.append(player_id)
        if availability_blocker:
            blockers.append(f"player_id={player_id}: {availability_blocker}")

        xg_adjusted = bool(row.get("xg90_low_sample_adjusted", False)) if pd.notna(row.get("xg90_low_sample_adjusted")) else False
        xa_adjusted = bool(row.get("xa90_low_sample_adjusted", False)) if pd.notna(row.get("xa90_low_sample_adjusted")) else False
        if xg_adjusted or xa_adjusted:
            adjusted_ids.append(player_id)

        base_row = base_by_id.get(player_id, {})
        evidence_rows.append(
            {
                "player_id": player_id,
                "web_name": row.get("web_name"),
                "historical_sample_class": history_class,
                "previous_minutes": _number(row, "previous_minutes", 0.0),
                "previous_starts": _number(row, "previous_starts", 0.0),
                "previous_appearances": _number(row, "previous_appearances", 0.0),
                "previous_role_games": _number(row, "previous_role_games", 0.0),
                "preseason_sample_class": preseason_class,
                "preseason_minutes": _number(row, "preseason_minutes", 0.0),
                "preseason_starts": _number(row, "preseason_starts", 0.0),
                "preseason_appearances": _number(row, "preseason_appearances", 0.0),
                "preseason_recency_evidence": _number(row, "preseason_recency_evidence", 0.0),
                "xg90_context_reliability": None if pd.isna(row.get("xg90_context_reliability")) else _number(row, "xg90_context_reliability"),
                "xa90_context_reliability": None if pd.isna(row.get("xa90_context_reliability")) else _number(row, "xa90_context_reliability"),
                "xg90_low_sample_adjusted": xg_adjusted,
                "xa90_low_sample_adjusted": xa_adjusted,
                "availability_evidence_state": availability_state,
                "minutes_class": base_row.get("minutes_class", "unknown"),
                "canonical_projection_gameweeks": base_row.get("canonical_projection_gameweeks", 0),
                "airsenal_projection_gameweeks": base_row.get("airsenal_projection_gameweeks", 0),
                "expected_projection_gameweeks": base_row.get("expected_projection_gameweeks", 0),
                "role_class": base_row.get("role_class", "unknown"),
                "set_piece_share_source": base_row.get("set_piece_share_source", "none"),
                "forecast_fields_are_not_facts": True,
            }
        )

    if weak_history_ids:
        warnings.append(
            f"{len(weak_history_ids)}/{len(players)} players have fewer than "
            f"{int(LOW_SAMPLE_ATTACK_MINUTES)} prior-league minutes; sample scarcity remains explicit"
        )
    if no_preseason_ids:
        warnings.append(
            f"{len(no_preseason_ids)}/{len(players)} players have no measured preseason appearance sample"
        )

    return {
        "contract": STATISTICAL_TRUTH_CONTRACT,
        "ready": not blockers,
        "as_of": as_of_ts.isoformat() if as_of_ts is not None else None,
        "player_count": int(len(players)),
        "expected_official_player_count": expected_players,
        "projection_rows": int(len(projections)),
        "projection_column": projection_col,
        "hard_fact_coverage": base.get("hard_fact_coverage"),
        "canonical_projection_pair_coverage": base.get("canonical_projection_pair_coverage"),
        "airsenal_projection_pair_coverage": base.get("airsenal_projection_pair_coverage"),
        "role_provenance_counts": role_counts,
        "minutes_provenance_classes": sorted(minutes_class),
        "historical_sample_classes": dict(sorted(history_counts.items())),
        "preseason_sample_classes": dict(sorted(preseason_counts.items())),
        "availability_evidence_states": dict(sorted(availability_counts.items())),
        "low_sample_attack_minutes_threshold": float(LOW_SAMPLE_ATTACK_MINUTES),
        "low_sample_attack_adjusted_player_count": len(set(adjusted_ids)),
        "low_sample_attack_adjusted_player_ids": sorted(set(adjusted_ids)),
        "players": evidence_rows,
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "base_player_truth_contract": base.get("contract"),
    }
