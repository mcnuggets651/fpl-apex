from __future__ import annotations

from pathlib import Path
import pandas as pd


def load_tactical_roles(path: Path) -> pd.DataFrame:
    """Load verified tactical-role overrides.

    The file is intentionally explicit instead of auto-guessing roles from names.
    role_multiplier is a modest attacking-role adjustment; 1.0 is neutral.
    """
    cols = ["player_id", "tactical_role", "role_multiplier", "role_confidence"]
    if not path.exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(path)
    if "player_id" not in df.columns:
        raise ValueError("tactical role file requires official player_id")
    out = df.copy()
    out["player_id"] = pd.to_numeric(out["player_id"], errors="raise").astype(int)
    if "tactical_role" not in out:
        out["tactical_role"] = "verified-role"
    if "role_multiplier" not in out:
        out["role_multiplier"] = 1.0
    if "role_confidence" not in out:
        out["role_confidence"] = 0.8
    out["role_multiplier"] = pd.to_numeric(out["role_multiplier"], errors="raise").clip(0.80, 1.20)
    out["role_confidence"] = pd.to_numeric(out["role_confidence"], errors="raise").clip(0, 1)
    return out[cols].drop_duplicates("player_id", keep="last")
