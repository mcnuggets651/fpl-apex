from __future__ import annotations

import pandas as pd

from apex_fpl.data.http import CachedHttp


class OddsAdapter:
    """Optional generic JSON odds adapter.

    Expected configured endpoint response is a list of objects with player_id and
    market_xp, or an object containing that list under `players`.
    """

    def __init__(self, http: CachedHttp, url: str | None, api_key: str | None):
        self.http, self.url, self.api_key = http, url, api_key

    def load(self, force: bool = False) -> pd.DataFrame:
        if not self.url:
            return pd.DataFrame(columns=["player_id", "market_xp"])
        params = {"apiKey": self.api_key} if self.api_key else None
        payload = self.http.get_json(self.url, "odds", force, params=params)
        rows = payload.get("players", []) if isinstance(payload, dict) else payload
        df = pd.DataFrame(rows)
        if not {"player_id", "market_xp"}.issubset(df.columns):
            return pd.DataFrame(columns=["player_id", "market_xp"])
        return df[["player_id", "market_xp"]]
