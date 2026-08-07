from __future__ import annotations

from pathlib import Path

import pandas as pd

ROLE_COLUMNS = [
    "player_id",
    "tactical_role",
    "role_multiplier",
    "role_confidence",
    "penalty_share",
    "corners_share",
    "direct_freekick_share",
    "indirect_freekick_share",
    "context_reason",
    "source_url",
    "updated_at",
]


def load_tactical_roles(path: Path) -> pd.DataFrame:
    """Load verified tactical/set-piece overrides keyed by official FPL ID.

    ``role_multiplier`` is deliberately modest. Optional set-piece shares are
    probabilities/shares from 0–1 and override the cruder official FPL order
    heuristic only when explicitly populated. The file cannot alter canonical
    club, FPL position, price or name.
    """
    if not path.exists():
        return pd.DataFrame(columns=ROLE_COLUMNS)
    df = pd.read_csv(path)
    if "player_id" not in df.columns:
        raise ValueError("tactical role file requires official player_id")

    forbidden = {"team", "team_name", "position", "price", "now_cost", "web_name"} & set(df.columns)
    if forbidden:
        raise ValueError(
            f"tactical role file cannot override canonical fields: {sorted(forbidden)}"
        )

    out = df.copy()
    out["player_id"] = pd.to_numeric(out["player_id"], errors="raise").astype(int)
    if "tactical_role" not in out:
        out["tactical_role"] = "verified-role"
    if "role_multiplier" not in out:
        out["role_multiplier"] = 1.0
    if "role_confidence" not in out:
        out["role_confidence"] = 0.8
    out["role_multiplier"] = pd.to_numeric(
        out["role_multiplier"], errors="raise"
    ).clip(0.80, 1.20)
    out["role_confidence"] = pd.to_numeric(
        out["role_confidence"], errors="raise"
    ).clip(0, 1)

    for col in [
        "penalty_share",
        "corners_share",
        "direct_freekick_share",
        "indirect_freekick_share",
    ]:
        if col not in out:
            out[col] = pd.NA
        out[col] = pd.to_numeric(out[col], errors="coerce").clip(0, 1)

    for col in ["context_reason", "source_url", "updated_at"]:
        if col not in out:
            out[col] = pd.NA

    return out[ROLE_COLUMNS].drop_duplicates("player_id", keep="last")
