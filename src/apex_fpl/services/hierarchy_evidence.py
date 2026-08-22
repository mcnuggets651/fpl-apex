from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from apex_fpl.services.evidence_time import current_evidence_rows
from apex_fpl.services.player_identity import resolve_source_identities


REQUIRED_HIERARCHY_COLUMNS = {
    "player_id",
    "hierarchy_status",
    "checked_at",
    "valid_until",
}


def load_current_hierarchy_evidence(
    players: pd.DataFrame,
    path: Path,
    *,
    now: datetime | None = None,
    strict_identity: bool = True,
) -> pd.DataFrame:
    """Load current manual hierarchy evidence against Official player identity.

    Historical/expired rows are retained in source control for auditability but never
    influence a current decision. Malformed chronology or ambiguous identity is a
    contract failure when ``strict_identity`` is true.
    """
    if not path.exists():
        return pd.DataFrame(columns=sorted(REQUIRED_HIERARCHY_COLUMNS | {"web_name"}))
    frame = pd.read_csv(path)
    missing = REQUIRED_HIERARCHY_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"{path} missing governed hierarchy columns: {sorted(missing)}")
    name_col = (
        "source_player_name"
        if "source_player_name" in frame.columns
        else "web_name"
        if "web_name" in frame.columns
        else None
    )
    if name_col is None:
        raise ValueError(f"{path} requires an independent player-name witness")

    frame = current_evidence_rows(
        frame,
        observed_col="checked_at",
        expires_col="valid_until",
        now=now,
        label="governed squad hierarchy",
        strict=True,
    )
    if frame.empty:
        return frame

    if not strict_identity:
        official_names = {
            int(row.player_id): str(row.web_name).strip().casefold()
            for row in players.itertuples(index=False)
            if hasattr(row, "web_name")
        }
        frame = frame[
            frame.apply(
                lambda row: official_names.get(int(row["player_id"]))
                == str(row[name_col]).strip().casefold(),
                axis=1,
            )
        ].copy()
        if frame.empty:
            return frame

    frame, identity = resolve_source_identities(
        players,
        frame,
        source="squad_hierarchy",
        name_columns=(name_col,),
        allow_name_fallback=False,
        require_identity_witness=True,
        raise_on_error=False,
    )
    if not identity.ready:
        raise ValueError(
            "squad hierarchy identity failed: " + "; ".join(identity.blockers[:10])
        )
    frame["hierarchy_status"] = (
        frame["hierarchy_status"].astype(str).str.strip().str.casefold()
    )
    return frame.reset_index(drop=True)
