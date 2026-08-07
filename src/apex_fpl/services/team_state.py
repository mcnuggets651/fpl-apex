from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml


@dataclass
class TeamState:
    squad: set[int]
    bank: float = 0.0
    free_transfers: int = 1


def load_team_state(
    squad_path: str | Path = "data/manual/current_squad.csv",
    state_path: str | Path = "data/manual/team_state.yaml",
) -> TeamState | None:
    squad_file = Path(squad_path)
    if not squad_file.exists():
        return None
    df = pd.read_csv(squad_file)
    if "player_id" not in df.columns:
        raise ValueError("current_squad.csv requires a player_id column")
    squad = set(pd.to_numeric(df["player_id"], errors="raise").astype(int).tolist())
    if len(squad) != 15:
        raise ValueError("current_squad.csv must contain exactly 15 unique player_id values")

    bank, free = 0.0, 1
    sf = Path(state_path)
    if sf.exists():
        raw = yaml.safe_load(sf.read_text()) or {}
        bank = float(raw.get("bank", 0.0))
        free = int(raw.get("free_transfers", 1))
    free = min(5, max(1, free))
    return TeamState(squad=squad, bank=bank, free_transfers=free)
