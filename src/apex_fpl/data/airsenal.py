from __future__ import annotations

from pathlib import Path

import pandas as pd

ALIASES = {
    "player_id": ("player_id", "element", "fpl_id", "player_code"),
    "gw": ("gw", "gameweek", "event"),
    "xp": ("xp", "xP", "expected_points", "prediction", "predicted_points"),
    "xmins": ("expected_minutes", "xMins", "xmins", "minutes"),
    "confidence": ("confidence",),
}


def _find(columns, field: str) -> str | None:
    return next((name for name in ALIASES[field] if name in columns), None)


class AIrsenalProjectionAdapter:
    """Read a genuine AIrsenal export without coupling Apex to its database schema."""

    def __init__(self, path: str | None):
        self.path = Path(path).expanduser() if path else None

    def available(self) -> bool:
        return bool(self.path and self.path.exists())

    def load(self, valid_ids: set[int] | None = None) -> pd.DataFrame:
        cols = ["player_id", "gw", "airsenal_xp", "airsenal_xmins", "airsenal_confidence"]
        if not self.available():
            return pd.DataFrame(columns=cols)
        df = pd.read_csv(self.path)
        pid_col, gw_col, xp_col = (_find(df.columns, x) for x in ("player_id", "gw", "xp"))
        if pid_col and gw_col and xp_col:
            out = pd.DataFrame({
                "player_id": pd.to_numeric(df[pid_col], errors="raise").astype(int),
                "gw": pd.to_numeric(df[gw_col], errors="raise").astype(int),
                "airsenal_xp": pd.to_numeric(df[xp_col], errors="raise").astype(float),
            })
            xm = _find(df.columns, "xmins")
            conf = _find(df.columns, "confidence")
            out["airsenal_xmins"] = pd.to_numeric(df[xm], errors="coerce") if xm else 90.0
            out["airsenal_confidence"] = pd.to_numeric(df[conf], errors="coerce") if conf else 1.0
        else:
            gw_cols = [c for c in df.columns if str(c).upper().startswith("GW")]
            if not pid_col or not gw_cols:
                raise ValueError(
                    "AIrsenal CSV must contain official player ID plus (gameweek, expected points) "
                    "or wide GW* columns"
                )
            long = df.melt(id_vars=[pid_col], value_vars=gw_cols, var_name="gw", value_name="airsenal_xp")
            long["player_id"] = pd.to_numeric(long[pid_col], errors="raise").astype(int)
            long["gw"] = long["gw"].astype(str).str.upper().str.replace("GW", "", regex=False).astype(int)
            out = long[["player_id", "gw", "airsenal_xp"]]
            out["airsenal_xmins"] = 90.0
            out["airsenal_confidence"] = 1.0
        out["airsenal_confidence"] = out["airsenal_confidence"].fillna(1.0).clip(0, 1)
        out["airsenal_xmins"] = out["airsenal_xmins"].fillna(90.0).clip(0, 180)
        if valid_ids is not None:
            unknown = sorted(set(out["player_id"]) - set(valid_ids))
            if unknown:
                raise ValueError(f"AIrsenal export contains unknown official FPL IDs: {unknown[:10]}")
        if (out["gw"] <= 0).any():
            raise ValueError("AIrsenal export contains invalid gameweek")
        return out.sort_values(["gw", "player_id"]).reset_index(drop=True)
