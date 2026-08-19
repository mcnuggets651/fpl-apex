from __future__ import annotations

import pandas as pd

from apex_fpl.services.player_identity import (
    activate_official_identity_registry,
    resolve_source_identities,
)


def _latest_core_snapshot(core: pd.DataFrame) -> pd.DataFrame:
    """Return one unambiguous current FPL Core row per official player."""
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
    """Attach FPL Core statistics only after official-FPL identity certification.

    Official FPL remains canonical. A Core row with an ID/name/team/position conflict
    is withheld completely rather than retaining statistics on a potentially wrong
    player. The identity report remains available to diagnostics.
    """
    o = official.copy()
    activate_official_identity_registry(o)
    c = _latest_core_snapshot(core)
    if c.empty:
        return o, pd.DataFrame(
            columns=["player_id", "field", "official", "external", "source"]
        )

    name_columns = tuple(
        col
        for col in ("web_name", "source_player_name", "player_name", "name")
        if col in c.columns
    )
    require_witness = bool(
        name_columns or {"first_name", "second_name"}.issubset(c.columns)
    )
    safe, identity = resolve_source_identities(
        o,
        c,
        source="fpl_core",
        name_columns=name_columns or ("source_player_name",),
        require_identity_witness=require_witness,
        allow_name_fallback=False,
        raise_on_error=False,
    )

    warnings: list[dict] = []
    if not identity.report.empty:
        bad = identity.report[~identity.report["status"].isin(["exact_id", "name_fallback"])]
        for row in bad.itertuples(index=False):
            pid = row.input_player_id
            try:
                player_id = int(float(pid))
            except (TypeError, ValueError):
                player_id = -1
            warnings.append(
                {
                    "player_id": player_id,
                    "field": "identity",
                    "official": "official_fpl",
                    "external": str(row.reason),
                    "source": "fpl_core",
                }
            )

    # The full Core snapshot normally carries independent name witnesses. If it does,
    # any conflict is a source-integrity failure rather than a soft warning.
    if require_witness and not identity.ready:
        raise ValueError(
            "FPL Core identity integrity failed; statistical rows withheld: "
            + "; ".join(identity.blockers[:10])
        )

    merge_cols = [col for col in safe.columns if col != "id"]
    merged = o.merge(
        safe[merge_cols],
        on="player_id",
        how="left",
        suffixes=("", "_core"),
        validate="one_to_one",
    )
    for col in [
        "web_name_core",
        "first_name_core",
        "second_name_core",
        "team_core",
        "team_name_core",
        "position_core",
        "price_core",
    ]:
        if col in merged:
            merged.drop(columns=col, inplace=True)
    return merged, pd.DataFrame(warnings)
