from __future__ import annotations

from pathlib import Path
import pandas as pd

CONTEXT_COLUMNS = [
    "player_id", "tactical_role", "role_attack_multiplier", "role_assist_multiplier",
    "start_probability", "expected_minutes_override", "rotation_risk", "injury_risk",
    "transfer_risk", "penalty_share", "set_piece_share", "manager_confidence",
    "context_confidence", "context_reason", "source", "source_url", "updated_at",
]


def load_player_context(path: str | Path = "data/manual/player_context.csv") -> pd.DataFrame:
    """Load auditable contextual evidence keyed only by official FPL ID."""
    p = Path(path)
    if not p.exists():
        return pd.DataFrame(columns=CONTEXT_COLUMNS)
    df = pd.read_csv(p)
    if "player_id" not in df.columns:
        raise ValueError("player_context.csv requires player_id")
    df["player_id"] = pd.to_numeric(df["player_id"], errors="raise").astype(int)
    illegal = {"team", "team_name", "position", "price", "now_cost", "web_name"} & set(df.columns)
    if illegal:
        raise ValueError(f"player_context.csv cannot override canonical fields: {sorted(illegal)}")
    for col in CONTEXT_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    return df[CONTEXT_COLUMNS]
