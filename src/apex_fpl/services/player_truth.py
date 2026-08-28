from __future__ import annotations

import pandas as pd

from apex_fpl.services.projection_registry import PROJECTION_PROVIDERS, normalise_provider_key, provider_spec


HARD_FACT_FIELDS = (
    "player_id", "web_name", "team", "team_name", "position", "price", "status",
)
ORDER_FIELDS = (
    "penalties_order", "corners_and_indirect_freekicks_order", "direct_freekicks_order",
)
SHARE_FIELDS = (
    "penalty_share", "corners_share", "direct_freekick_share", "indirect_freekick_share",
)
TRUSTED_SOURCE_TIERS = {"official_club", "official_league", "trusted_media"}


def _text(row: pd.Series, column: str) -> str:
    value = row.get(column)
    return "" if pd.isna(value) else str(value).strip()


def _minutes_class(row: pd.Series) -> str:
    if pd.notna(row.get("expected_minutes_override")):
        return "sourced_current_override"
    current_matches = pd.to_numeric(pd.Series([row.get("current_team_matches")]), errors="coerce").fillna(0).iloc[0]
    if float(current_matches) > 0:
        return "forecast_current_season"
    preseason_apps = pd.to_numeric(pd.Series([row.get("preseason_appearances")]), errors="coerce").fillna(0).iloc[0]
    if float(preseason_apps) > 0:
        return "forecast_historical_plus_preseason"
    return "forecast_historical_prior"


def _pair_coverage(
    projections: pd.DataFrame,
    player_ids: set[int],
    gameweeks: list[int],
    *,
    value_column: str | None = None,
) -> tuple[float, dict[int, int], list[tuple[int, int]]]:
    expected = len(player_ids) * len(gameweeks)
    if expected == 0 or not {"player_id", "gw"}.issubset(projections.columns):
        return 0.0, {}, []
    rows = projections[projections["gw"].astype(int).isin(gameweeks)].copy()
    rows["player_id"] = pd.to_numeric(rows["player_id"], errors="coerce")
    rows["gw"] = pd.to_numeric(rows["gw"], errors="coerce")
    rows = rows.dropna(subset=["player_id", "gw"])
    rows["player_id"] = rows["player_id"].astype(int)
    rows["gw"] = rows["gw"].astype(int)
    rows = rows[rows["player_id"].isin(player_ids)]
    if value_column is not None:
        if value_column not in rows.columns:
            return 0.0, {}, sorted((pid, gw) for pid in player_ids for gw in gameweeks)
        values = pd.to_numeric(rows[value_column], errors="coerce")
        rows = rows.loc[values.notna() & values.ge(0)]
    pairs = rows[["player_id", "gw"]].drop_duplicates()
    pair_set = set(map(tuple, pairs.itertuples(index=False, name=None)))
    expected_set = {(pid, gw) for pid in player_ids for gw in gameweeks}
    missing = sorted(expected_set - pair_set)
    counts = pairs.groupby("player_id")["gw"].nunique().astype(int).to_dict()
    return len(pair_set) / expected, counts, missing


def audit_player_truth(
    players: pd.DataFrame,
    projections: pd.DataFrame,
    expected_players: int | None,
    *,
    champion_provider: str = "airsenal",
) -> dict:
    """Audit factual completeness and production projection identity for all players.

    Official FPL owns hard facts. The selected forecast champion must cover every
    Official player/Gameweek pair with a genuine provider value. No fallback to Apex or
    another provider is permitted. Challenger coverage is measured only for diagnostics.
    """
    champion = normalise_provider_key(champion_provider)
    champion_spec = provider_spec(champion)
    blockers: list[str] = []
    warnings: list[str] = []

    missing_columns = [field for field in HARD_FACT_FIELDS if field not in players.columns]
    if missing_columns:
        blockers.append(f"missing canonical hard-fact columns: {missing_columns}")

    duplicate_ids = int(players["player_id"].duplicated().sum()) if "player_id" in players.columns else len(players)
    if duplicate_ids:
        blockers.append(f"official player_id is not unique: {duplicate_ids} duplicate rows")
    if expected_players is not None and len(players) != expected_players:
        blockers.append(f"player truth universe mismatch: reports={len(players)} official_snapshot={expected_players}")

    hard_complete = pd.Series(True, index=players.index)
    for field in HARD_FACT_FIELDS:
        if field not in players.columns:
            hard_complete &= False
            continue
        if field in {"web_name", "team_name", "position", "status"}:
            hard_complete &= players[field].notna() & players[field].astype(str).str.strip().ne("")
        else:
            hard_complete &= pd.to_numeric(players[field], errors="coerce").notna()
    hard_coverage = float(hard_complete.mean()) if len(players) else 0.0
    if hard_coverage < 1.0:
        blockers.append(f"canonical hard-fact coverage is {hard_coverage:.2%}, required 100%")

    valid_ids = set(pd.to_numeric(players.get("player_id"), errors="coerce").dropna().astype(int))
    gameweeks = sorted(pd.to_numeric(projections.get("gw"), errors="coerce").dropna().astype(int).unique().tolist())
    projection_coverage, projection_counts, missing_projection_pairs = _pair_coverage(
        projections, valid_ids, gameweeks, value_column="xp"
    )
    if projection_coverage < 1.0:
        blockers.append(
            f"canonical projection pair coverage is {projection_coverage:.2%}, required 100%; "
            f"missing={missing_projection_pairs[:20]}"
        )

    champion_coverage, champion_counts, missing_champion_pairs = _pair_coverage(
        projections,
        valid_ids,
        gameweeks,
        value_column=champion_spec.xp_column,
    )
    if champion_coverage < 1.0:
        blockers.append(
            f"production champion {champion_spec.display_name} pair coverage is "
            f"{champion_coverage:.2%}, required 100%; missing={missing_champion_pairs[:20]}; "
            "silent provider fallback is forbidden"
        )

    projection_provider_keys = set(
        projections.get("projection_provider_key", pd.Series(dtype=str))
        .dropna()
        .astype(str)
        .str.casefold()
    )
    if projection_provider_keys and projection_provider_keys != {champion}:
        blockers.append(
            f"projection authority mismatch: configured champion={champion}, "
            f"surface providers={sorted(projection_provider_keys)}"
        )

    provider_coverages: dict[str, float] = {}
    provider_counts: dict[str, dict[int, int]] = {}
    for key, spec in PROJECTION_PROVIDERS.items():
        column = "apex_shadow_xp" if key == "apex" else spec.xp_column
        coverage, counts, _ = _pair_coverage(
            projections,
            valid_ids,
            gameweeks,
            value_column=column,
        )
        provider_coverages[key] = coverage
        provider_counts[key] = counts
        if key != champion and coverage < 1.0:
            warnings.append(
                f"shadow provider {spec.display_name} coverage={coverage:.2%}; "
                "shadow coverage cannot block production"
            )

    projection_set_piece = pd.DataFrame()
    if not projections.empty and {"player_id", "xp_set_piece_prior"}.issubset(projections.columns):
        projection_set_piece = (
            projections.assign(
                xp_set_piece_prior=pd.to_numeric(
                    projections["xp_set_piece_prior"], errors="coerce"
                ).fillna(0.0)
            )
            .groupby("player_id", as_index=False)["xp_set_piece_prior"]
            .sum()
            .rename(columns={"xp_set_piece_prior": "set_piece_xp_horizon"})
        )

    rows: list[dict] = []
    unverified_share_ids: list[int] = []
    unexplained_set_piece_xp_ids: list[int] = []
    inferred_roles = 0

    for idx, row in players.iterrows():
        player_id = int(row["player_id"]) if pd.notna(row.get("player_id")) else -1
        explicit = {
            field: (None if pd.isna(row.get(field)) else float(row.get(field)))
            for field in SHARE_FIELDS
        }
        has_explicit_share = any(value is not None and value > 0 for value in explicit.values())
        source_tier = _text(row, "source_tier")
        source_url = _text(row, "source_url")
        evidence_type = _text(row, "lineup_evidence_type")
        verified_share = bool(
            has_explicit_share
            and source_tier in TRUSTED_SOURCE_TIERS
            and source_url.startswith(("https://", "http://"))
            and evidence_type
        )
        if has_explicit_share and not verified_share:
            unverified_share_ids.append(player_id)

        role_source = _text(row, "tactical_role_source") or "statistical_inference"
        role_class = "sourced_current_override" if role_source == "verified_override" else "statistical_inference"
        inferred_roles += int(role_class == "statistical_inference")

        set_piece_xp = 0.0
        if not projection_set_piece.empty and player_id >= 0:
            match = projection_set_piece[
                pd.to_numeric(projection_set_piece["player_id"], errors="coerce").eq(player_id)
            ]
            if not match.empty:
                set_piece_xp = float(match.iloc[0]["set_piece_xp_horizon"])
        if set_piece_xp > 1e-9 and not verified_share:
            unexplained_set_piece_xp_ids.append(player_id)

        rows.append({
            "player_id": player_id,
            "web_name": row.get("web_name"),
            "hard_fact_complete": bool(hard_complete.loc[idx]),
            "identity_price_position_source": "official_fpl",
            "canonical_projection_gameweeks": int(projection_counts.get(player_id, 0)),
            "champion_provider": champion,
            "champion_projection_gameweeks": int(champion_counts.get(player_id, 0)),
            "expected_projection_gameweeks": len(gameweeks),
            "provider_projection_gameweeks": {
                key: int(counts.get(player_id, 0))
                for key, counts in provider_counts.items()
            },
            "penalties_order": row.get("penalties_order"),
            "corners_and_indirect_freekicks_order": row.get("corners_and_indirect_freekicks_order"),
            "direct_freekicks_order": row.get("direct_freekicks_order"),
            "set_piece_order_source": "official_fpl",
            **explicit,
            "set_piece_share_source": (
                "verified_current_override"
                if verified_share
                else "unverified"
                if has_explicit_share
                else "none"
            ),
            "set_piece_xp_horizon": set_piece_xp,
            "tactical_role": row.get("tactical_role"),
            "role_class": role_class,
            "role_confidence": row.get("role_confidence"),
            "expected_minutes": row.get("expected_minutes"),
            "minutes_confidence": row.get("minutes_confidence"),
            "minutes_class": _minutes_class(row),
            "forecast_fields_are_not_facts": True,
        })

    if unverified_share_ids:
        blockers.append(
            "explicit set-piece shares without trusted current provenance: "
            + ",".join(map(str, sorted(set(unverified_share_ids))[:30]))
        )
    if unexplained_set_piece_xp_ids:
        blockers.append(
            "set-piece xP exists without verified explicit share evidence: "
            + ",".join(map(str, sorted(set(unexplained_set_piece_xp_ids))[:30]))
        )
    if inferred_roles:
        warnings.append(
            f"{inferred_roles}/{len(players)} tactical roles are statistical inference; "
            "this is forecast uncertainty, not a factual-data failure"
        )

    return {
        "contract": "apex-player-truth-v2",
        "ready": not blockers,
        "player_count": len(players),
        "expected_official_player_count": expected_players,
        "gameweeks": gameweeks,
        "hard_fact_coverage": hard_coverage,
        "canonical_projection_pair_coverage": projection_coverage,
        "champion_provider": champion,
        "champion_provider_display_name": champion_spec.display_name,
        "champion_projection_pair_coverage": champion_coverage,
        "provider_projection_pair_coverage": provider_coverages,
        "hard_fact_fields": list(HARD_FACT_FIELDS),
        "ordinal_set_piece_fields": list(ORDER_FIELDS),
        "explicit_share_fields": list(SHARE_FIELDS),
        "inferred_role_count": inferred_roles,
        "blockers": blockers,
        "warnings": list(dict.fromkeys(warnings)),
        "players": rows,
    }
