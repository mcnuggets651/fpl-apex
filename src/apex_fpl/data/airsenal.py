from __future__ import annotations

from pathlib import Path

import pandas as pd


class AIrsenalProjectionAdapter:
    """Read an AIrsenal projection export without coupling Apex to AIrsenal internals."""

    def __init__(self, path: str | None):
        self.path = Path(path).expanduser() if path else None

    def available(self) -> bool:
        return bool(self.path and self.path.exists())

    def load(self) -> pd.DataFrame:
        if not self.available():
            return pd.DataFrame(columns=["player_id", "gw", "airsenal_xp"])
        df = pd.read_csv(self.path)
        if {"player_id", "gw", "xp"}.issubset(df.columns):
            return df[["player_id", "gw", "xp"]].rename(columns={"xp": "airsenal_xp"})
        gw_cols = [c for c in df.columns if str(c).upper().startswith("GW")]
        if "player_id" not in df.columns or not gw_cols:
            raise ValueError("AIrsenal CSV must contain player_id plus (gw,xp) or GW* columns")
        long = df.melt(id_vars=["player_id"], value_vars=gw_cols, var_name="gw", value_name="airsenal_xp")
        long["gw"] = long["gw"].astype(str).str.upper().str.replace("GW", "", regex=False).astype(int)
        return long
