from __future__ import annotations

import pandas as pd

from apex_fpl.data.http import CachedHttp
from apex_fpl.data.official import OfficialFPLClient
from apex_fpl.services.player_identity import resolve_source_identities


class OddsAdapter:
    """Optional generic JSON odds adapter with fail-closed player identity.

    A configured player-level endpoint must provide ``player_id``, ``market_xp`` and
    an independent player-name witness (``source_player_name``, ``player_name``,
    ``web_name`` or ``name``). A numerically valid FPL ID is not sufficient evidence
    that the market row belongs to that player.
    """

    def __init__(self, http: CachedHttp, url: str | None, api_key: str | None):
        self.http, self.url, self.api_key = http, url, api_key

    def load(self, force: bool = False) -> pd.DataFrame:
        columns = ["player_id", "market_xp", "source_player_name"]
        if not self.url:
            return pd.DataFrame(columns=columns)
        params = {"apiKey": self.api_key} if self.api_key else None
        payload = self.http.get_json(self.url, "odds", force, params=params)
        rows = payload.get("players", []) if isinstance(payload, dict) else payload
        df = pd.DataFrame(rows)
        if not {"player_id", "market_xp"}.issubset(df.columns):
            return pd.DataFrame(columns=columns)

        name_col = next(
            (
                col
                for col in ("source_player_name", "player_name", "web_name", "name")
                if col in df.columns
            ),
            None,
        )
        if name_col is None:
            raise ValueError(
                "configured player-level odds require an independent player-name witness"
            )
        work = df[["player_id", "market_xp", name_col]].copy()
        work = work.rename(columns={name_col: "source_player_name"})
        work["market_xp"] = pd.to_numeric(work["market_xp"], errors="raise").astype(float)
        if work["market_xp"].isna().any():
            raise ValueError("odds market_xp contains missing values")

        official = OfficialFPLClient(self.http).snapshot(force=force).players
        safe, result = resolve_source_identities(
            official,
            work,
            source="market_odds",
            name_columns=("source_player_name",),
            allow_name_fallback=False,
            require_identity_witness=True,
            raise_on_error=False,
        )
        if not result.ready:
            raise ValueError(
                "market odds identity integrity failed: "
                + "; ".join(result.blockers[:10])
            )
        if safe["player_id"].duplicated().any():
            raise ValueError("market odds contain duplicate player_id rows")
        return safe[columns].reset_index(drop=True)
