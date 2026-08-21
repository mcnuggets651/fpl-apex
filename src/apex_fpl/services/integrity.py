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
        sample = c.loc[c.duplicated(["player_id", "gw"], keep=False), ["player_id", "gw"]].drop_duplicates().head(10).to_dict("records")
        raise ValueError(f"FPL Core playerstats contains ambiguous duplicate player/GW snapshots: {sample}")
    c["player_id"] = c["player_id"].astype(int)
    c["gw"] = c["gw"].astype(int)
    return c.sort_values(["player_id", "gw"]).drop_duplicates("player_id", keep="last").reset_index(drop=True)


def _prepare_core_identity_witness(core: pd.DataFrame) -> tuple[pd.DataFrame, tuple[str, ...], bool]:
    """Prefer Core full names over lossy/ambiguous display names when available."""
    c = core.copy()
    has_full_name = {"first_name", "second_name"}.issubset(c.columns)
    if has_full_name:
        first = c["first_name"].fillna("").astype(str).str.strip()
        second = c["second_name"].fillna("").astype(str).str.strip()
        full = (first + " " + second).str.strip()
        c["source_full_name"] = full.where(full.ne(""), pd.NA)
    name_columns = tuple(col for col in ("source_full_name", "source_player_name", "player_name", "name", "web_name") if col in c.columns)
    return c, name_columns, bool(name_columns or has_full_name)


def reconcile(official: pd.DataFrame, core: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Attach FPL Core statistics only after official-FPL identity certification."""
    o = official.copy()
    activate_official_identity_registry(o)
    c = _latest_core_snapshot(core)
    if c.empty:
        return o, pd.DataFrame(columns=["player_id", "field", "official", "external", "source"])

    c, name_columns, require_witness = _prepare_core_identity_witness(c)
    safe, identity = resolve_source_identities(
        o, c, source="fpl_core", name_columns=name_columns or ("source_player_name",),
        require_identity_witness=require_witness, allow_name_fallback=False, raise_on_error=False,
    )

    warnings: list[dict] = []
    if not identity.report.empty:
        bad = identity.report[~identity.report["status"].isin(["exact_id", "name_fallback"])]
        for row in bad.itertuples(index=False):
            try:
                player_id = int(float(row.input_player_id))
            except (TypeError, ValueError):
                player_id = -1
            warnings.append({"player_id": player_id, "field": "identity", "official": "official_fpl", "external": str(row.reason), "source": "fpl_core"})

    if require_witness and not identity.ready:
        raise ValueError("FPL Core identity integrity failed; statistical rows withheld: " + "; ".join(identity.blockers[:10]))

    merge_cols = [col for col in safe.columns if col != "id"]
    merged = o.merge(safe[merge_cols], on="player_id", how="left", suffixes=("", "_core"), validate="one_to_one")
    if "price_core" in merged:
        merged.drop(columns=["price_core"], inplace=True)
    return merged, pd.DataFrame(warnings)
