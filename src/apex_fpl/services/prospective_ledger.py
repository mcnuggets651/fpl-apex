from __future__ import annotations

from typing import Any

import pandas as pd


PROVIDER_COLUMNS = {
    "AIrsenal": "airsenal_xp",
    "Apex proprietary": "apex_shadow_xp",
    "Official FPL EP": "official_xp",
}


def provider_ledger_from_forecast(
    forecast: pd.DataFrame,
    *,
    season: str,
    source_versions: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Normalize one frozen pre-deadline forecast into immutable provider rows."""
    versions = source_versions or {}
    rows: list[dict[str, Any]] = []
    for provider, column in PROVIDER_COLUMNS.items():
        if column not in forecast.columns:
            continue
        for record in forecast.to_dict("records"):
            value = pd.to_numeric(pd.Series([record.get(column)]), errors="coerce").iloc[0]
            if pd.isna(value):
                continue
            rows.append({
                "season": season,
                "gw": int(record["gw"]),
                "deadline_timestamp": record.get("deadline_time"),
                "forecast_timestamp": record.get("forecast_generated_at"),
                "official_snapshot_id": record.get("official_snapshot_id"),
                "player_id": int(record["player_id"]),
                "provider": provider,
                "provider_version": versions.get(provider, ""),
                "authority": "production" if provider == "AIrsenal" else "shadow",
                "xp": float(value),
                "expected_minutes": record.get("expected_minutes"),
                "start_probability": record.get("start_probability"),
                "appearance_probability": record.get("appearance_probability"),
                "position": record.get("position"),
                "price": record.get("price"),
                "club": record.get("team_name"),
            })
    return pd.DataFrame(rows)
