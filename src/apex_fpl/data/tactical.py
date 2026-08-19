from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from apex_fpl.services.player_identity import (
    active_official_identity_registry,
    resolve_source_identities,
)

ROLE_COLUMNS = [
    "player_id",
    "source_player_name",
    "tactical_role",
    "role_multiplier",
    "role_confidence",
    "penalty_share",
    "corners_share",
    "direct_freekick_share",
    "indirect_freekick_share",
    "expected_minutes_override",
    "start_probability_override",
    "appearance_probability_override",
    "minutes_evidence_confidence",
    "lineup_evidence_type",
    "context_reason",
    "source_name",
    "source_tier",
    "source_url",
    "published_at",
    "retrieved_at",
    "expires_at",
]

TRUSTED_SOURCE_TIERS = {"official_club", "official_league", "trusted_media"}
MATERIAL_OVERRIDE_COLUMNS = (
    "penalty_share",
    "corners_share",
    "direct_freekick_share",
    "indirect_freekick_share",
    "expected_minutes_override",
    "start_probability_override",
    "appearance_probability_override",
)


def load_tactical_roles(
    path: Path,
    *,
    now: datetime | None = None,
) -> pd.DataFrame:
    """Load verified tactical/set-piece overrides keyed by official FPL ID.

    Every non-empty player-linked override must carry an independent player-name
    witness and reconcile to the active Official-FPL registry before any role,
    minutes or set-piece value can reach the model surface.
    """
    if not path.exists():
        return pd.DataFrame(columns=ROLE_COLUMNS)
    df = pd.read_csv(path)
    if "player_id" not in df.columns:
        raise ValueError("tactical role file requires official player_id")
    if not df.empty and "source_player_name" not in df.columns:
        raise ValueError("tactical role file requires independent source_player_name")

    forbidden = {"team", "team_name", "position", "price", "now_cost", "web_name"} & set(df.columns)
    if forbidden:
        raise ValueError(
            f"tactical role file cannot override canonical fields: {sorted(forbidden)}"
        )

    out = df.copy()
    out["player_id"] = pd.to_numeric(out["player_id"], errors="raise").astype(int)
    if "source_player_name" not in out:
        out["source_player_name"] = pd.NA
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
        "start_probability_override",
        "appearance_probability_override",
        "minutes_evidence_confidence",
    ]:
        if col not in out:
            out[col] = pd.NA
        out[col] = pd.to_numeric(out[col], errors="coerce").clip(0, 1)

    if "expected_minutes_override" not in out:
        out["expected_minutes_override"] = pd.NA
    out["expected_minutes_override"] = pd.to_numeric(
        out["expected_minutes_override"], errors="coerce"
    ).clip(0, 90)

    for col in [
        "lineup_evidence_type",
        "context_reason",
        "source_name",
        "source_tier",
        "source_url",
        "published_at",
        "expires_at",
    ]:
        if col not in out:
            out[col] = pd.NA

    material = (
        out[list(MATERIAL_OVERRIDE_COLUMNS)].notna().any(axis=1)
        | out["role_multiplier"].ne(1.0)
        | out["tactical_role"].astype(str).ne("verified-role")
    )
    now_value = pd.Timestamp(now or datetime.now(timezone.utc))
    now_utc = (
        now_value.tz_localize("UTC")
        if now_value.tzinfo is None
        else now_value.tz_convert("UTC")
    )
    for idx, row in out.loc[material].iterrows():
        if str(row["source_tier"]).strip() not in TRUSTED_SOURCE_TIERS:
            raise ValueError(f"tactical override row {idx} has untrusted source_tier")
        if not str(row["source_name"]).strip() or not str(row["source_url"]).startswith(
            ("https://", "http://")
        ):
            raise ValueError(f"tactical override row {idx} lacks verifiable provenance")
        if not str(row["lineup_evidence_type"]).strip():
            raise ValueError(f"tactical override row {idx} lacks evidence type")
        published = pd.to_datetime(row["published_at"], utc=True, errors="coerce")
        expires = pd.to_datetime(row["expires_at"], utc=True, errors="coerce")
        if pd.isna(published) or pd.isna(expires):
            raise ValueError(
                f"tactical override row {idx} requires valid published_at and expires_at"
            )
        if expires <= published:
            raise ValueError(f"tactical override row {idx} expires before publication")
        if now_utc > expires:
            raise ValueError(f"tactical override row {idx} is expired")

    out["retrieved_at"] = now_utc.isoformat()
    if not out.empty:
        registry = active_official_identity_registry()
        if registry is None:
            raise ValueError(
                "tactical role identity validation requires active Official-FPL registry"
            )
        safe, result = resolve_source_identities(
            registry,
            out,
            source="manual_tactical_roles",
            name_columns=("source_player_name",),
            allow_name_fallback=False,
            require_identity_witness=True,
            raise_on_error=False,
        )
        if not result.ready:
            raise ValueError(
                "tactical role identity integrity failed: "
                + "; ".join(result.blockers[:10])
            )
        out = safe

    return out[ROLE_COLUMNS].drop_duplicates("player_id", keep="last")
