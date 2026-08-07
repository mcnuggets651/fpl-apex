from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ALIASES = {
    "player_id": ("player_id", "element", "fpl_id", "player_code"),
    "gw": ("gw", "gameweek", "event"),
    "xp": ("xp", "xP", "expected_points", "prediction", "predicted_points"),
    "xmins": ("expected_minutes", "xMins", "xmins", "minutes"),
    "confidence": ("confidence",),
}
METADATA_COLUMNS = ("generated_at", "source_version", "prediction_tag")


def _find(columns, field: str) -> str | None:
    return next((name for name in ALIASES[field] if name in columns), None)


def _metadata(df: pd.DataFrame, index: pd.Index) -> pd.DataFrame:
    result = pd.DataFrame(index=index)
    for col in METADATA_COLUMNS:
        if col in df.columns:
            result[col] = df[col].values
        else:
            result[col] = pd.NA
    return result


class AIrsenalProjectionAdapter:
    """Read a genuine AIrsenal export without coupling Apex to its DB schema.

    The canonical contract is one row per official FPL ``player_id`` / Gameweek.
    AIrsenal's own internal ``player.player_id`` must never enter this adapter; the
    exporter joins to ``player.fpl_api_id`` first.
    """

    def __init__(self, path: str | None):
        self.path = Path(path).expanduser() if path else None

    def available(self) -> bool:
        return bool(self.path and self.path.exists())

    def load(self, valid_ids: set[int] | None = None) -> pd.DataFrame:
        cols = [
            "player_id",
            "gw",
            "airsenal_xp",
            "airsenal_xmins",
            "airsenal_confidence",
            *METADATA_COLUMNS,
        ]
        if not self.available():
            return pd.DataFrame(columns=cols)

        df = pd.read_csv(self.path)
        pid_col, gw_col, xp_col = (_find(df.columns, x) for x in ("player_id", "gw", "xp"))
        if pid_col and gw_col and xp_col:
            out = pd.DataFrame(
                {
                    "player_id": pd.to_numeric(df[pid_col], errors="raise").astype(int),
                    "gw": pd.to_numeric(df[gw_col], errors="raise").astype(int),
                    "airsenal_xp": pd.to_numeric(df[xp_col], errors="raise").astype(float),
                }
            )
            xm = _find(df.columns, "xmins")
            conf = _find(df.columns, "confidence")
            out["airsenal_xmins"] = (
                pd.to_numeric(df[xm], errors="coerce") if xm else pd.Series(pd.NA, index=df.index)
            )
            out["airsenal_confidence"] = (
                pd.to_numeric(df[conf], errors="coerce")
                if conf
                else pd.Series(pd.NA, index=df.index)
            )
            out = pd.concat([out, _metadata(df, out.index)], axis=1)
        else:
            gw_cols = [c for c in df.columns if str(c).upper().startswith("GW")]
            if not pid_col or not gw_cols:
                raise ValueError(
                    "AIrsenal CSV must contain official player ID plus (gameweek, expected points) "
                    "or wide GW* columns"
                )
            id_vars = [pid_col, *[c for c in METADATA_COLUMNS if c in df.columns]]
            long = df.melt(
                id_vars=id_vars,
                value_vars=gw_cols,
                var_name="gw",
                value_name="airsenal_xp",
            )
            long["player_id"] = pd.to_numeric(long[pid_col], errors="raise").astype(int)
            long["gw"] = (
                long["gw"].astype(str).str.upper().str.replace("GW", "", regex=False).astype(int)
            )
            out = long[["player_id", "gw", "airsenal_xp"]].copy()
            out["airsenal_xmins"] = pd.NA
            out["airsenal_confidence"] = pd.NA
            for col in METADATA_COLUMNS:
                out[col] = long[col] if col in long.columns else pd.NA

        out["airsenal_xmins"] = pd.to_numeric(out["airsenal_xmins"], errors="coerce")
        out["airsenal_confidence"] = pd.to_numeric(out["airsenal_confidence"], errors="coerce")
        if valid_ids is not None:
            unknown = sorted(set(out["player_id"]) - set(valid_ids))
            if unknown:
                raise ValueError(
                    "AIrsenal export contains unknown official FPL IDs. This commonly means "
                    f"AIrsenal internal IDs were exported by mistake: {unknown[:10]}"
                )
        if (out["gw"] <= 0).any():
            raise ValueError("AIrsenal export contains invalid gameweek")
        if out.duplicated(["player_id", "gw"]).any():
            duplicate = out.loc[out.duplicated(["player_id", "gw"], keep=False), ["player_id", "gw"]]
            sample = duplicate.drop_duplicates().head(10).to_dict("records")
            raise ValueError(
                "AIrsenal export must be aggregated to one row per official player/Gameweek; "
                f"duplicates include {sample}"
            )
        return out.sort_values(["gw", "player_id"]).reset_index(drop=True)


def validate_airsenal_forecast(
    forecast: pd.DataFrame,
    valid_ids: set[int],
    gameweeks: list[int],
    *,
    expected_source_version: str = "",
    max_age_hours: float = 36.0,
    min_player_coverage: float = 0.95,
) -> tuple[bool, str]:
    """Validate that an AIrsenal file is genuine, current and horizon-complete."""
    if forecast.empty:
        return False, "genuine projection export not configured"

    unknown = sorted(set(forecast["player_id"].astype(int)) - set(valid_ids))
    if unknown:
        return False, f"unknown official FPL IDs: {unknown[:10]}"

    requested = set(map(int, gameweeks))
    covered = set(pd.to_numeric(forecast["gw"], errors="coerce").dropna().astype(int)) & requested
    missing = sorted(requested - covered)
    if missing:
        return False, f"missing requested Gameweeks: {missing}"

    xp = pd.to_numeric(forecast["airsenal_xp"], errors="coerce")
    if xp.isna().any() or not np.isfinite(xp).all():
        return False, "expected-points surface contains non-finite values"
    if (xp < 0).any() or (xp > 40).any():
        sample = forecast.loc[(xp < 0) | (xp > 40), ["player_id", "gw", "airsenal_xp"]]
        return False, f"expected-points values outside [0, 40]: {sample.head(5).to_dict('records')}"

    if "airsenal_xmins" in forecast and forecast["airsenal_xmins"].notna().any():
        xmins = pd.to_numeric(forecast["airsenal_xmins"], errors="coerce")
        invalid_xmins = xmins.notna() & (~np.isfinite(xmins) | (xmins < 0) | (xmins > 180))
        if invalid_xmins.any():
            return False, "expected-minutes values outside [0, 180]"
    if "airsenal_confidence" in forecast and forecast["airsenal_confidence"].notna().any():
        confidence = pd.to_numeric(forecast["airsenal_confidence"], errors="coerce")
        invalid_confidence = confidence.notna() & (
            ~np.isfinite(confidence) | ~confidence.between(0, 1, inclusive="both")
        )
        if invalid_confidence.any():
            return False, "confidence values outside [0, 1]"

    min_players = max(1, int(len(valid_ids) * min_player_coverage))
    coverage = forecast[forecast["gw"].isin(gameweeks)].groupby("gw")["player_id"].nunique()
    thin = {int(gw): int(count) for gw, count in coverage.items() if int(count) < min_players}
    if thin:
        return False, f"insufficient official-player coverage; expected >= {min_players} per GW, got {thin}"

    if "generated_at" not in forecast or forecast["generated_at"].isna().all():
        return False, "missing generated_at provenance; re-export with scripts/export_airsenal.py"
    generated = pd.to_datetime(forecast["generated_at"], utc=True, errors="coerce")
    if generated.isna().all():
        return False, "invalid generated_at provenance"
    newest = generated.max()
    now = datetime.now(timezone.utc)
    age_hours = (now - newest.to_pydatetime()).total_seconds() / 3600
    if age_hours < -0.25:
        return False, f"forecast timestamp is {abs(age_hours):.1f}h in the future"
    if age_hours > max_age_hours:
        return False, f"AIrsenal forecast is stale ({age_hours:.1f}h old; max {max_age_hours:.1f}h)"

    versions = {
        str(value).strip()
        for value in forecast.get("source_version", pd.Series(dtype=str)).dropna().tolist()
        if str(value).strip()
    }
    if expected_source_version:
        if not versions:
            return False, "missing source_version provenance; pinned AIrsenal commit cannot be verified"
        if versions != {expected_source_version}:
            return False, (
                f"AIrsenal version mismatch: expected {expected_source_version}, "
                f"found {sorted(versions)}"
            )

    tags = {
        str(value).strip()
        for value in forecast.get("prediction_tag", pd.Series(dtype=str)).dropna().tolist()
        if str(value).strip()
    }
    if not tags:
        return False, "missing prediction_tag provenance"
    if len(tags) != 1:
        return False, f"export mixes multiple AIrsenal prediction tags: {sorted(tags)}"

    counts = {int(gw): int(count) for gw, count in coverage.items()}
    return True, (
        f"{len(forecast)} rows; player coverage={counts}; age={max(age_hours, 0):.1f}h; "
        f"tag={next(iter(tags))}"
    )
