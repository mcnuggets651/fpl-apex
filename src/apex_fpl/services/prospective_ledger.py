from __future__ import annotations

from typing import Any

import pandas as pd

from apex_fpl.services.projection_registry import PROJECTION_PROVIDERS, normalise_provider_key


ADDITIONAL_PROVIDER_COLUMNS = {
    "Official FPL EP": "official_xp",
}


def provider_ledger_from_forecast(
    forecast: pd.DataFrame,
    *,
    season: str,
    champion_provider: str = "airsenal",
    source_versions: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Normalize one frozen pre-deadline forecast into immutable provider rows.

    Authority is derived from the explicit champion key, never inferred from whichever
    provider happened to be present. This keeps shadow providers measurable without
    allowing them to acquire production authority by accident.
    """
    champion = normalise_provider_key(champion_provider)
    versions = source_versions or {}
    rows: list[dict[str, Any]] = []
    provider_columns = {
        spec.display_name: (key, "apex_shadow_xp" if key == "apex" else spec.xp_column)
        for key, spec in PROJECTION_PROVIDERS.items()
    }
    provider_columns.update(
        {name: ("", column) for name, column in ADDITIONAL_PROVIDER_COLUMNS.items()}
    )

    for provider_name, (provider_key, column) in provider_columns.items():
        if column not in forecast.columns:
            continue
        for record in forecast.to_dict("records"):
            value = pd.to_numeric(pd.Series([record.get(column)]), errors="coerce").iloc[0]
            if pd.isna(value):
                continue
            authority = (
                "production"
                if provider_key and provider_key == champion
                else "shadow"
            )
            prefix = provider_key if provider_key else ""
            rows.append({
                "season": season,
                "gw": int(record["gw"]),
                "deadline_timestamp": record.get("deadline_time"),
                "forecast_timestamp": record.get("forecast_generated_at"),
                "official_snapshot_id": record.get("official_snapshot_id"),
                "player_id": int(record["player_id"]),
                "provider": provider_name,
                "provider_key": provider_key,
                "provider_version": versions.get(provider_name, ""),
                "authority": authority,
                "xp": float(value),
                "expected_minutes": record.get(
                    f"{prefix}_xmins" if prefix else "expected_minutes",
                    record.get("expected_minutes"),
                ),
                "start_probability": record.get(
                    f"{prefix}_p_start" if prefix else "start_probability",
                    record.get("start_probability"),
                ),
                "appearance_probability": record.get(
                    f"{prefix}_p_any" if prefix else "appearance_probability",
                    record.get("appearance_probability"),
                ),
                "minutes_60_plus_probability": record.get(
                    f"{prefix}_p60" if prefix else "minutes_60_plus_probability",
                    record.get("minutes_60_plus_probability"),
                ),
                "position": record.get("position"),
                "price": record.get("price"),
                "club": record.get("team_name"),
            })
    return pd.DataFrame(rows)
