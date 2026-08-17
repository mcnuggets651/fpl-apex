from __future__ import annotations

import pandas as pd


def _latest_core_snapshot(core: pd.DataFrame) -> pd.DataFrame:
    """Return one unambiguous current FPL Core row per official player.

    FPL Core stores longitudinal player snapshots as the season progresses. Current
    production needs only the newest cumulative row for each player; historical
    consumers still retain the raw longitudinal source outside this reconciliation
    step. Ambiguous duplicate player/GW rows fail closed rather than being averaged.
    """
    c = core.copy()
    if c.empty or "player_id" not in c.columns or not c["player_id"].duplicated().any():
        return c
    if "gw" not in c.columns:
        raise ValueError("longitudinal FPL Core playerstats lacks Gameweek keys")
    c["player_id"] = pd.to_numeric(c["player_id"], errors="coerce")
    c["gw"] = pd.to_numeric(c["gw"], errors="coerce")
    if c[["player_id", "gw"]].isna().any().any():
        raise ValueError("FPL Core playerstats contains invalid player/GW keys")
    if c.duplicated(["player_id", "gw"]).any():
        sample = (
            c.loc[c.duplicated(["player_id", "gw"], keep=False), ["player_id", "gw"]]
            .drop_duplicates()
            .head(10)
            .to_dict("records")
        )
        raise ValueError(
            "FPL Core playerstats contains ambiguous duplicate player/GW snapshots: "
            f"{sample}"
        )
    c["player_id"] = c["player_id"].astype(int)
    c["gw"] = c["gw"].astype(int)
    return (
        c.sort_values(["player_id", "gw"])
        .drop_duplicates("player_id", keep="last")
        .reset_index(drop=True)
    )


def reconcile(official: pd.DataFrame, core: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Official identity always wins; external conflicts are reported."""
    o = official.copy()
    c = _latest_core_snapshot(core)
    if c.empty:
        return o, pd.DataFrame(
            columns=["player_id", "field", "official", "external", "source"]
        )
    merge_cols = [col for col in c.columns if col != "id"]
    merged = o.merge(
        c[merge_cols],
        on="player_id",
        how="left",
        suffixes=("", "_core"),
        validate="one_to_one",
    )
    warnings = []
    checks = [
        ("web_name", "web_name_core"),
        ("team", "team_core"),
        ("position", "position_core"),
    ]
    for left, right in checks:
        if left in merged and right in merged:
            mismatch = merged[right].notna() & (
                merged[left].astype(str) != merged[right].astype(str)
            )
            for _, row in merged.loc[mismatch, ["player_id", left, right]].iterrows():
                warnings.append(
                    {
                        "player_id": int(row["player_id"]),
                        "field": left,
                        "official": row[left],
                        "external": row[right],
                        "source": "fpl_core",
                    }
                )
    # Remove conflicting auxiliary identity fields while retaining statistical enrichment.
    for col in ["web_name_core", "team_core", "position_core", "price_core"]:
        if col in merged:
            merged.drop(columns=col, inplace=True)
    return merged, pd.DataFrame(warnings)
