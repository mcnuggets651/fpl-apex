from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from apex_fpl.services.projection_registry import provider_spec


ALIASES = {
    "player_id": ("player_id", "element", "fpl_id", "fpl_element_id"),
    "gw": ("gw", "gameweek", "event"),
    "xp": ("xp", "xP", "xpts", "xPts", "expected_points", "prediction", "predicted_points"),
    "xmins": ("expected_minutes", "xMins", "xmins", "minutes"),
    "p_start": ("p_start", "start_probability"),
    "p_any": ("p_any", "appearance_probability"),
    "p60": ("p60", "minutes_60_plus_probability", "p_60"),
    "confidence": ("confidence", "projection_confidence"),
    "sd": ("projection_sd", "forecast_sd", "sd"),
}
METADATA_COLUMNS = ("generated_at", "source_version", "prediction_tag")


def _find(columns, field: str) -> str | None:
    return next((name for name in ALIASES[field] if name in columns), None)


class ExternalProjectionAdapter:
    """Normalize an external provider export onto Official-FPL player/Gameweek IDs.

    The adapter intentionally does not accept provider-specific internal identifiers.
    A forecast becomes eligible for Apex only after it is keyed to current Official FPL
    element IDs, preserving the same identity protection used by the production solve.
    """

    def __init__(self, path: str | None, provider_key: str):
        self.path = Path(path).expanduser() if path else None
        self.spec = provider_spec(provider_key)

    def available(self) -> bool:
        return bool(self.path and self.path.exists())

    def load(self, valid_ids: set[int] | None = None) -> pd.DataFrame:
        prefix = self.spec.key
        columns = [
            "player_id",
            "gw",
            self.spec.xp_column,
            f"{prefix}_xmins",
            f"{prefix}_p_start",
            f"{prefix}_p_any",
            f"{prefix}_p60",
            f"{prefix}_confidence",
            f"{prefix}_sd",
            *METADATA_COLUMNS,
        ]
        if not self.available():
            return pd.DataFrame(columns=columns)

        raw = pd.read_csv(self.path)
        pid_col = _find(raw.columns, "player_id")
        gw_col = _find(raw.columns, "gw")
        xp_col = _find(raw.columns, "xp")
        if not pid_col or not gw_col or not xp_col:
            raise ValueError(
                f"{self.spec.display_name} CSV must contain Official FPL player ID, "
                "Gameweek and expected points"
            )

        out = pd.DataFrame(
            {
                "player_id": pd.to_numeric(raw[pid_col], errors="raise").astype(int),
                "gw": pd.to_numeric(raw[gw_col], errors="raise").astype(int),
                self.spec.xp_column: pd.to_numeric(raw[xp_col], errors="raise").astype(float),
            }
        )
        for field, suffix in (
            ("xmins", "xmins"),
            ("p_start", "p_start"),
            ("p_any", "p_any"),
            ("p60", "p60"),
            ("confidence", "confidence"),
            ("sd", "sd"),
        ):
            source_col = _find(raw.columns, field)
            target = f"{prefix}_{suffix}"
            out[target] = (
                pd.to_numeric(raw[source_col], errors="coerce")
                if source_col
                else pd.Series(pd.NA, index=raw.index)
            )
        for column in METADATA_COLUMNS:
            out[column] = raw[column].values if column in raw.columns else pd.NA

        if valid_ids is not None:
            unknown = sorted(set(out["player_id"]) - set(valid_ids))
            if unknown:
                raise ValueError(
                    f"{self.spec.display_name} export contains unknown Official FPL IDs: "
                    f"{unknown[:10]}"
                )
        if (out["gw"] <= 0).any():
            raise ValueError(f"{self.spec.display_name} export contains invalid Gameweek")
        if out.duplicated(["player_id", "gw"]).any():
            sample = (
                out.loc[
                    out.duplicated(["player_id", "gw"], keep=False),
                    ["player_id", "gw"],
                ]
                .drop_duplicates()
                .head(10)
                .to_dict("records")
            )
            raise ValueError(
                f"{self.spec.display_name} export must contain one row per Official "
                f"player/Gameweek; duplicates include {sample}"
            )
        return out.sort_values(["gw", "player_id"]).reset_index(drop=True)


def validate_external_forecast(
    forecast: pd.DataFrame,
    provider_key: str,
    valid_ids: set[int],
    gameweeks: list[int],
    *,
    expected_source_version: str = "",
    max_age_hours: float = 36.0,
    min_player_coverage: float = 0.0,
    require_provenance: bool = True,
) -> tuple[bool, str]:
    """Validate structural integrity, freshness and horizon coverage of a provider export."""
    spec = provider_spec(provider_key)
    if forecast.empty:
        return False, f"{spec.display_name} projection export not configured"

    unknown = sorted(set(forecast["player_id"].astype(int)) - set(valid_ids))
    if unknown:
        return False, f"unknown Official FPL IDs: {unknown[:10]}"

    requested = set(map(int, gameweeks))
    covered = set(pd.to_numeric(forecast["gw"], errors="coerce").dropna().astype(int)) & requested
    missing = sorted(requested - covered)
    if missing:
        return False, f"missing requested Gameweeks: {missing}"

    xp = pd.to_numeric(forecast[spec.xp_column], errors="coerce")
    if xp.isna().any() or not np.isfinite(xp).all():
        return False, "expected-points surface contains non-finite values"
    if (xp < 0).any() or (xp > 40).any():
        sample = forecast.loc[(xp < 0) | (xp > 40), ["player_id", "gw", spec.xp_column]]
        return False, f"expected-points values outside [0, 40]: {sample.head(5).to_dict('records')}"

    prefix = spec.key
    xmins_col = f"{prefix}_xmins"
    if xmins_col in forecast and forecast[xmins_col].notna().any():
        xmins = pd.to_numeric(forecast[xmins_col], errors="coerce")
        bad = xmins.notna() & (~np.isfinite(xmins) | (xmins < 0) | (xmins > 180))
        if bad.any():
            return False, "expected-minutes values outside [0, 180]"
    for suffix in ("p_start", "p_any", "p60", "confidence"):
        column = f"{prefix}_{suffix}"
        if column not in forecast or not forecast[column].notna().any():
            continue
        values = pd.to_numeric(forecast[column], errors="coerce")
        bad = values.notna() & (~np.isfinite(values) | ~values.between(0, 1, inclusive="both"))
        if bad.any():
            return False, f"{column} values outside [0, 1]"
    sd_col = f"{prefix}_sd"
    if sd_col in forecast and forecast[sd_col].notna().any():
        values = pd.to_numeric(forecast[sd_col], errors="coerce")
        bad = values.notna() & (~np.isfinite(values) | (values < 0))
        if bad.any():
            return False, f"{sd_col} contains invalid uncertainty values"

    min_players = max(1, int(np.ceil(len(valid_ids) * max(float(min_player_coverage), 0.0))))
    coverage = forecast[forecast["gw"].isin(gameweeks)].groupby("gw")["player_id"].nunique()
    if min_player_coverage > 0:
        thin = {int(gw): int(count) for gw, count in coverage.items() if int(count) < min_players}
        if thin:
            return False, f"insufficient Official-player coverage; expected >= {min_players} per GW, got {thin}"

    requested_rows = forecast[forecast["gw"].isin(gameweeks)]
    generated_at = ""
    age_hours: float | None = None
    if require_provenance:
        if "generated_at" not in requested_rows or requested_rows["generated_at"].isna().any():
            return False, "missing generated_at provenance"
        generated = pd.to_datetime(requested_rows["generated_at"], utc=True, errors="coerce")
        if generated.isna().any():
            return False, "invalid generated_at provenance"
        generations = generated.drop_duplicates()
        if len(generations) != 1:
            return False, "export mixes multiple provider generations across required rows"
        newest = generations.iloc[0]
        generated_at = newest.isoformat()
        age_hours = (datetime.now(timezone.utc) - newest.to_pydatetime()).total_seconds() / 3600
        if age_hours < -0.25:
            return False, f"forecast timestamp is {abs(age_hours):.1f}h in the future"
        if age_hours > max_age_hours:
            return False, f"{spec.display_name} forecast is stale ({age_hours:.1f}h old; max {max_age_hours:.1f}h)"

        versions = {
            str(value).strip()
            for value in requested_rows.get("source_version", pd.Series(dtype=str)).dropna().tolist()
            if str(value).strip()
        }
        if expected_source_version:
            if not versions:
                return False, "missing source_version provenance; pinned provider commit cannot be verified"
            if versions != {expected_source_version}:
                return False, (
                    f"{spec.display_name} version mismatch: expected {expected_source_version}, "
                    f"found {sorted(versions)}"
                )
        tags = {
            str(value).strip()
            for value in requested_rows.get("prediction_tag", pd.Series(dtype=str)).dropna().tolist()
            if str(value).strip()
        }
        if not tags:
            return False, "missing prediction_tag provenance"
        if len(tags) != 1:
            return False, f"export mixes multiple prediction tags: {sorted(tags)}"

    counts = {int(gw): int(count) for gw, count in coverage.items()}
    age_note = f"; age={max(age_hours or 0.0, 0.0):.1f}h" if age_hours is not None else ""
    generated_note = f"; generated_at={generated_at}" if generated_at else ""
    return True, (
        f"{len(forecast)} rows; player coverage={counts}{age_note}{generated_note}"
    )
