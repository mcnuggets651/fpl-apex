from __future__ import annotations

import pandas as pd


def reconcile(official: pd.DataFrame, core: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Official identity always wins; external conflicts are reported."""
    o = official.copy()
    c = core.copy()
    if c.empty:
        return o, pd.DataFrame(columns=["player_id", "field", "official", "external", "source"])
    merge_cols = [c for c in c.columns if c != "id"]
    merged = o.merge(c[merge_cols], on="player_id", how="left", suffixes=("", "_core"))
    warnings = []
    checks = [("web_name", "web_name_core"), ("team", "team_core"), ("position", "position_core")]
    for left, right in checks:
        if left in merged and right in merged:
            mismatch = merged[right].notna() & (merged[left].astype(str) != merged[right].astype(str))
            for _, r in merged.loc[mismatch, ["player_id", left, right]].iterrows():
                warnings.append({"player_id": int(r["player_id"]), "field": left, "official": r[left], "external": r[right], "source": "fpl_core"})
    # Remove conflicting auxiliary identity fields while retaining statistical enrichment.
    for col in ["web_name_core", "team_core", "position_core", "price_core"]:
        if col in merged:
            merged.drop(columns=col, inplace=True)
    return merged, pd.DataFrame(warnings)
