from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from apex_fpl.config import Settings
from apex_fpl.data.airsenal import AIrsenalProjectionAdapter, validate_airsenal_forecast
from apex_fpl.data.core_insights import FPLCoreClient
from apex_fpl.data.http import CachedHttp
from apex_fpl.data.news import collect_news_sources, load_manual_signals
from apex_fpl.data.odds import OddsAdapter
from apex_fpl.data.official import OfficialFPLClient
from apex_fpl.data.tactical import load_tactical_roles
from apex_fpl.data.understat import load_understat_history, season_start_year
from apex_fpl.models.ensemble import blend_projection
from apex_fpl.models.fixtures import fixture_multipliers
from apex_fpl.models.minutes import minutes_profile
from apex_fpl.models.projection import project_players
from apex_fpl.models.shrinkage import (
    VALIDATED_ATTACK_PRIOR_MINUTES,
    RateShrinkageConfig,
    shrink_player_rates,
)
from apex_fpl.models.tactical import infer_tactical_roles
from apex_fpl.models.team_goals import build_team_goal_surface, build_team_ratings
from apex_fpl.optimisation.squad import optimise_squad
from apex_fpl.optimisation.transfers import TransferPlan, optimise_transfer_plan
from apex_fpl.reporting.writer import write_reports
from apex_fpl.services.data_quality import (
    DataQualityAssessment,
    assess_data_quality,
    official_strength_is_usable,
)
from apex_fpl.services.enrichment import add_preseason_features, coalesce_context
from apex_fpl.services.integrity import reconcile
from apex_fpl.services.news_signals import infer_news_signals
from apex_fpl.services.provenance import SourceStatus, load_upstream_pins
from apex_fpl.services.safety import SafetyAssessment, assess_safety
from apex_fpl.services.snapshots import write_official_snapshot
from apex_fpl.services.team_state import (
    TeamStateResolution,
    persist_initial_prices,
    resolve_team_state,
    write_team_state_report,
)


@dataclass
class PipelineOutput:
    players: pd.DataFrame
    projections: pd.DataFrame
    integrity: pd.DataFrame
    news_audit: pd.DataFrame
    scenarios: dict
    transfer_plan: TransferPlan | None
    sources: list[SourceStatus]
    gameweeks: list[int]
    safety: SafetyAssessment
    snapshot: dict
    data_quality: DataQualityAssessment
    team_state: TeamStateResolution | None = None


def _apply_validated_attack_shrinkage(
    players: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply only the attacking rates that passed untouched holdout gates."""
    out = players.copy()
    positions = out.get(
        "position",
        pd.Series("UNKNOWN", index=out.index, dtype="string"),
    ).astype("string")
    if "price" in out.columns:
        live_price = pd.to_numeric(out["price"], errors="coerce")
    elif "now_cost" in out.columns:
        live_price = pd.to_numeric(out["now_cost"], errors="coerce") / 10.0
    else:
        live_price = pd.Series(np.nan, index=out.index, dtype=float)
    price_rank = (
        live_price.groupby(positions)
        .rank(method="average", pct=True)
        .fillna(0.5)
    )
    price_tier = pd.cut(
        price_rank,
        bins=[-np.inf, 1 / 3, 2 / 3, np.inf],
        labels=["LOW", "MID", "HIGH"],
    ).astype("string")
    out["shrinkage_group"] = positions + "|" + price_tier

    audit = shrink_player_rates(
        out,
        RateShrinkageConfig(
            prior_minutes={
                "xg90": VALIDATED_ATTACK_PRIOR_MINUTES["xg90"],
                "xa90": VALIDATED_ATTACK_PRIOR_MINUTES["xa90"],
                # DEFCON remains unchanged until its separate gate passes.
                "defcon90": 0.0,
            },
            min_group_players=5,
            min_group_minutes=900.0,
        ),
    )
    out["unshrunk_expected_goals_per_90"] = pd.to_numeric(
        out.get("expected_goals_per_90"), errors="coerce"
    )
    out["unshrunk_expected_assists_per_90"] = pd.to_numeric(
        out.get("expected_assists_per_90"), errors="coerce"
    )
    out["expected_goals_per_90"] = audit["shrunk_xg90"].to_numpy(float)
    out["expected_assists_per_90"] = audit["shrunk_xa90"].to_numpy(float)
    for column in audit.columns:
        if column.startswith(("raw_", "prior_", "shrunk_", "xg90_", "xa90_")):
            out[f"shrinkage_{column}"] = audit[column].to_numpy()
    return out, audit


def _official_ep(players: pd.DataFrame, gameweeks: list[int]) -> pd.DataFrame:
    if not gameweeks:
        return pd.DataFrame(columns=["player_id", "gw", "official_xp"])
    ep = pd.to_numeric(players.get("ep_next", np.nan), errors="coerce")
    return pd.DataFrame(
        {"player_id": players["player_id"], "gw": gameweeks[0], "official_xp": ep}
    )


def _status(
    name: str,
    ok: bool,
    detail: str = "",
    configured: bool = True,
    version: str = "",
) -> SourceStatus:
    return SourceStatus(
        name=name,
        ok=ok,
        detail=detail,
        configured=configured,
        version=version,
    )


def _decision_gameweeks(events: pd.DataFrame, horizon: int) -> list[int]:
    """Return the next Gameweeks whose deadlines are still actionable.

    The old unfinished-event rule could optimise transfers for a Gameweek whose
    deadline had already passed. For a decision engine the correct horizon starts
    at the next open deadline, while pre-GW1 naturally starts at GW1.
    """
    if not events.empty and "deadline_time" in events.columns:
        deadlines = pd.to_datetime(events["deadline_time"], utc=True, errors="coerce")
        now = pd.Timestamp.now(tz="UTC")
        open_ids = (
            events.loc[deadlines > now, "id"]
            .dropna()
            .astype(int)
            .sort_values()
            .tolist()
        )
        if open_ids:
            return open_ids[:horizon]
    if not events.empty and {"id", "finished"}.issubset(events.columns):
        return (
            events.loc[events["finished"] == False, "id"]  # noqa: E712
            .dropna()
            .astype(int)
            .sort_values()
            .head(horizon)
            .tolist()
        )
    return []


def _summarise_horizons(proj: pd.DataFrame, gws: list[int]) -> pd.DataFrame:
    pids = proj[["player_id"]].drop_duplicates().copy()
    for horizon in (1, 3, 5, 8):
        chosen = gws[: min(horizon, len(gws))]
        vals = (
            proj[proj["gw"].isin(chosen)]
            .groupby("player_id")["weighted_xp"]
            .sum()
        )
        pids[f"xpts_{horizon}"] = pids["player_id"].map(vals).fillna(0)
    conf = proj.groupby("player_id")["projection_confidence"].mean()
    pids["projection_confidence"] = pids["player_id"].map(conf).fillna(0)
    return pids


def run_pipeline(
    settings: Settings,
    horizon: int | None = None,
    scenario: str = "both",
    force: bool = False,
    plan_transfers: bool = True,
) -> PipelineOutput:
    horizon = horizon or settings.horizon
    http = CachedHttp(settings.cache_dir)
    sources: list[SourceStatus] = []
    pins = load_upstream_pins(settings.upstreams_lock_path)

    official = OfficialFPLClient(http).snapshot(force=force)
    manifest = write_official_snapshot(official, settings.snapshot_dir)
    sources.append(
        _status(
            "official_fpl",
            True,
            f"{len(official.players)} players; {len(official.fixtures)} fixtures; "
            f"snapshot={manifest['snapshot_id']}",
            version=official.bootstrap_sha256[:12],
        )
    )

    # Capture the pre-GW1 official price universe while it is still possible. It
    # allows later public-entry runs to reconstruct the correct FPL selling price
    # for players retained from the initial squad.
    persist_initial_prices(
        official.players,
        official.events,
        settings.cache_dir,
    )

    team_resolution: TeamStateResolution | None = None
    if plan_transfers or settings.fpl_entry_id:
        team_resolution = resolve_team_state(
            http=http,
            players=official.players,
            events=official.events,
            cache_dir=settings.cache_dir,
            current_squad_path=settings.current_squad_path,
            team_state_path=settings.team_state_path,
            entry_id=settings.fpl_entry_id,
            force=force,
        )
        write_team_state_report(settings.report_dir, team_resolution)
        sources.append(
            _status(
                "team_state",
                team_resolution.ok,
                team_resolution.detail,
                configured=team_resolution.configured,
            )
        )

    core = pd.DataFrame(columns=["player_id"])
    previous = pd.DataFrame(columns=["player_id"])
    friendlies = pd.DataFrame()
    core_client: FPLCoreClient | None = None
    core_pin = str(pins.get("fpl_core_insights", {}).get("commit", ""))
    try:
        core_client = FPLCoreClient(http, settings.season, ref=core_pin or "main")
        core = core_client.playerstats(force=force)
        sources.append(
            _status(
                "fpl_core_playerstats",
                True,
                f"{len(core)} rows",
                version=core_pin,
            )
        )
        try:
            previous = core_client.previous_season_playerstats(force=force)
            previous_coverage = (
                pd.to_numeric(previous.get("previous_minutes"), errors="coerce")
                .notna()
                .mean()
            )
            sources.append(
                _status(
                    "fpl_core_previous_season",
                    previous_coverage >= 0.70,
                    f"{len(previous)} current official IDs; prior playing-time "
                    f"coverage={previous_coverage:.1%}",
                    version=core_pin,
                )
            )
        except Exception as exc:
            sources.append(
                _status("fpl_core_previous_season", False, str(exc), version=core_pin)
            )
        try:
            friendlies = core_client.preseason_friendlies(force=force)
            sources.append(
                _status(
                    "fpl_core_preseason",
                    True,
                    f"{len(friendlies)} player-match rows",
                    version=core_pin,
                )
            )
        except Exception as exc:
            sources.append(
                _status("fpl_core_preseason", False, str(exc), version=core_pin)
            )
    except Exception as exc:
        sources.append(
            _status("fpl_core_playerstats", False, str(exc), version=core_pin)
        )

    players, integrity = reconcile(official.players, core)
    if not previous.empty:
        previous = previous.drop_duplicates("player_id")
        players = players.merge(
            previous,
            on="player_id",
            how="left",
            validate="one_to_one",
        )
    players = coalesce_context(players)
    players = add_preseason_features(players, friendlies)

    inferred_roles = infer_tactical_roles(players)
    players = players.merge(inferred_roles, on="player_id", how="left")
    sources.append(
        _status(
            "tactical_inference",
            True,
            f"{inferred_roles['inferred_tactical_role'].notna().sum()} inferred player roles",
        )
    )

    manual = load_manual_signals()
    if not manual.empty:
        players = players.merge(manual, on="player_id", how="left")
        sources.append(_status("manual_availability", True, f"{len(manual)} rows"))
    else:
        sources.append(
            _status(
                "manual_availability",
                True,
                "not configured",
                configured=False,
            )
        )

    tactical = load_tactical_roles(settings.tactical_roles_path)
    if not tactical.empty:
        unknown = sorted(set(tactical.player_id) - set(players.player_id))
        if unknown:
            raise ValueError(
                f"tactical role file contains unknown official FPL IDs: {unknown[:10]}"
            )
        players = players.merge(tactical, on="player_id", how="left")
        sources.append(
            _status(
                "tactical_roles",
                True,
                f"{len(tactical)} verified role/set-piece overrides",
            )
        )
    else:
        sources.append(
            _status(
                "tactical_roles",
                True,
                "no verified overrides",
                configured=False,
            )
        )

    manual_role_mult = (
        pd.to_numeric(players["role_multiplier"], errors="coerce")
        if "role_multiplier" in players
        else pd.Series(np.nan, index=players.index)
    )
    manual_role_conf = (
        pd.to_numeric(players["role_confidence"], errors="coerce")
        if "role_confidence" in players
        else pd.Series(np.nan, index=players.index)
    )
    manual_role_label = (
        players["tactical_role"].astype("string")
        if "tactical_role" in players
        else pd.Series(pd.NA, index=players.index, dtype="string")
    )
    inferred_mult = pd.to_numeric(
        players.get(
            "inferred_role_multiplier",
            pd.Series(1.0, index=players.index),
        ),
        errors="coerce",
    ).fillna(1.0)
    inferred_conf = pd.to_numeric(
        players.get(
            "inferred_role_confidence",
            pd.Series(0.45, index=players.index),
        ),
        errors="coerce",
    ).fillna(0.45)
    inferred_label = players.get(
        "inferred_tactical_role",
        pd.Series("unknown", index=players.index, dtype="string"),
    ).astype("string")
    players["role_multiplier"] = manual_role_mult.fillna(inferred_mult).clip(
        0.80, 1.20
    )
    players["role_confidence"] = manual_role_conf.fillna(inferred_conf).clip(0, 1)
    players["tactical_role"] = manual_role_label.fillna(inferred_label)
    players["tactical_role_source"] = np.where(
        manual_role_label.notna(),
        "verified_override",
        "statistical_inference",
    )

    news_audit = pd.DataFrame()
    if settings.news_feeds:
        try:
            collection = collect_news_sources(settings.news_feeds)
            headlines = collection.items
            news_signal, news_audit = infer_news_signals(players, headlines)
            if not news_signal.empty:
                players = players.merge(news_signal, on="player_id", how="left")
            failed_detail = (
                f"; {len(collection.failed)} source(s) failed but healthy evidence retained"
                if collection.failed
                else ""
            )
            sources.append(
                _status(
                    "news_feeds",
                    True,
                    f"{len(headlines)} headlines; {len(news_audit)} player matches; "
                    f"{len(collection.succeeded)} source(s) healthy{failed_detail}",
                )
            )
        except Exception as exc:
            sources.append(
                _status("news_feeds", False, str(exc), configured=True)
            )
    else:
        sources.append(
            _status("news_feeds", True, "not configured", configured=False)
        )

    if "finished" in official.fixtures.columns:
        completed_fixtures = official.fixtures[
            official.fixtures["finished"].fillna(False).astype(bool)
        ]
        team_matches = pd.concat(
            [completed_fixtures["team_h"], completed_fixtures["team_a"]]
        ).value_counts()
        players["current_team_matches"] = players["team"].map(team_matches).fillna(0)
    else:
        players["current_team_matches"] = 0

    players, shrinkage_audit = _apply_validated_attack_shrinkage(players)
    attack_coverage = float(
        shrinkage_audit[["shrunk_xg90", "shrunk_xa90"]]
        .notna()
        .all(axis=1)
        .mean()
    )
    sources.append(
        _status(
            "empirical_bayes_attacking_rates",
            attack_coverage >= 0.95,
            f"validated xG90/xA90 coverage={attack_coverage:.1%}; "
            "DEFCON excluded from promotion",
            configured=True,
            version="position-price-tier-v1",
        )
    )

    profile = minutes_profile(players)
    for col in profile.columns:
        players[col] = profile[col]

    gws = _decision_gameweeks(official.events, horizon)
    if not gws:
        raise RuntimeError("Official FPL API returned no future actionable gameweeks")

    core_elos = pd.DataFrame()
    if core_client is not None:
        try:
            core_elos = core_client.fixture_elos(gws, force=force)
            sources.append(
                _status(
                    "fpl_core_elo",
                    not core_elos.empty,
                    f"{len(core_elos)} team-fixture Elo rows"
                    if not core_elos.empty
                    else "no reconciled Elo rows for requested horizon",
                    version=core_pin,
                )
            )
        except Exception as exc:
            sources.append(_status("fpl_core_elo", False, str(exc), version=core_pin))

    strength_ok, strength_detail = official_strength_is_usable(official.teams)
    sources.append(
        _status(
            "official_team_strength",
            strength_ok,
            strength_detail,
            configured=True,
            version=official.bootstrap_sha256[:12],
        )
    )
    relevant_fixture_sides = (
        len(official.fixtures[official.fixtures["event"].isin(gws)]) * 2
    )
    elo_rows = (
        len(core_elos[["gw", "team", "opponent", "is_home"]].drop_duplicates())
        if not core_elos.empty
        and {"gw", "team", "opponent", "is_home"}.issubset(core_elos.columns)
        else 0
    )
    elo_complete = relevant_fixture_sides > 0 and elo_rows >= relevant_fixture_sides
    understat_ratings = pd.DataFrame()
    understat_surface = pd.DataFrame()
    understat_complete = False
    understat_production = settings.understat_team_model_mode == "production"
    if settings.understat_enabled:
        active_year = season_start_year(settings.season)
        first_year = max(2018, active_year - settings.understat_history_seasons)
        try:
            history = load_understat_history(
                range(first_year, active_year + 1),
                active_season=active_year,
                cache_dir=settings.cache_dir / "understat",
                refresh_active=force,
            )
            understat_ratings = build_team_ratings(history.matches, official.teams)
            understat_surface = build_team_goal_surface(
                official.fixtures,
                understat_ratings,
                gws,
            )
            understat_rows = len(
                understat_surface[["gw", "team", "opponent", "is_home"]]
                .drop_duplicates()
            )
            understat_complete = (
                relevant_fixture_sides > 0 and understat_rows >= relevant_fixture_sides
            )
            promoted = int(
                (understat_ratings["prior_type"] == "promoted_league_average").sum()
            )
            note = f"; {'; '.join(history.warnings)}" if history.warnings else ""
            sources.append(
                _status(
                    "understat_team_model",
                    understat_complete,
                    f"{len(history.matches)} completed-match rows across "
                    f"{len(history.completed_seasons)} complete seasons; "
                    f"fixture coverage={understat_rows}/{relevant_fixture_sides}; "
                    f"promoted/unknown priors={promoted}; "
                    f"mode={settings.understat_team_model_mode}{note}",
                )
            )
        except Exception as exc:
            sources.append(_status("understat_team_model", False, str(exc)))
    else:
        sources.append(
            _status(
                "understat_team_model",
                True,
                "disabled by configuration",
                configured=False,
            )
        )

    active_understat = understat_complete and understat_production
    fixture_model_ok = active_understat or strength_ok or elo_complete
    if strength_ok:
        fixture_detail = (
            "Understat xG model is active with official strength as corroboration"
            if active_understat
            else "positive, varying official team strengths are active"
        )
    elif active_understat:
        fixture_detail = (
            f"official strength unavailable ({strength_detail}); complete Understat xG "
            f"team-goal surface is active ({relevant_fixture_sides}/{relevant_fixture_sides})"
        )
    elif elo_complete:
        fixture_detail = (
            f"official strength unavailable ({strength_detail}); using league goal baselines "
            f"plus complete reconciled Elo coverage ({elo_rows}/{relevant_fixture_sides}); "
            f"Understat challenger mode={settings.understat_team_model_mode}"
        )
    else:
        fixture_detail = (
            f"official strength unavailable ({strength_detail}); reconciled Elo coverage "
            f"is incomplete ({elo_rows}/{relevant_fixture_sides})"
        )
    sources.append(_status("fixture_model", fixture_model_ok, fixture_detail))

    fx = fixture_multipliers(
        official.fixtures,
        official.teams,
        gws,
        core_elos=core_elos,
        use_official_strength=strength_ok,
        team_goal_surface=understat_surface if active_understat else None,
    )
    apex = project_players(players, fx, gws)
    projection_context = players[
        ["player_id", "minutes_confidence", "role_confidence"]
    ]
    proj = apex.merge(
        projection_context,
        on="player_id",
        how="left",
    ).merge(
        _official_ep(players, gws),
        on=["player_id", "gw"],
        how="left",
    )

    air_adapter = AIrsenalProjectionAdapter(settings.airsenal_csv)
    air_pin = str(pins.get("airsenal", {}).get("commit", ""))
    try:
        air = air_adapter.load(valid_ids=set(players.player_id.astype(int)))
        if not air.empty:
            air_ok, air_detail = validate_airsenal_forecast(
                air,
                set(players.player_id.astype(int)),
                gws,
                expected_source_version=air_pin,
                max_age_hours=settings.max_airsenal_age_hours,
                min_player_coverage=settings.min_airsenal_player_coverage,
            )
            if air_ok:
                proj = proj.merge(air, on=["player_id", "gw"], how="left")
            sources.append(
                _status(
                    "airsenal",
                    air_ok,
                    air_detail,
                    configured=True,
                    version=air_pin,
                )
            )
        elif settings.airsenal_csv:
            sources.append(
                _status(
                    "airsenal",
                    False,
                    f"configured forecast file missing or empty: {settings.airsenal_csv}",
                    configured=True,
                    version=air_pin,
                )
            )
        else:
            sources.append(
                _status(
                    "airsenal",
                    True,
                    "genuine projection export not configured",
                    configured=False,
                    version=air_pin,
                )
            )
    except Exception as exc:
        sources.append(
            _status(
                "airsenal",
                False,
                str(exc),
                configured=bool(settings.airsenal_csv),
                version=air_pin,
            )
        )

    try:
        odds = OddsAdapter(
            http,
            settings.odds_api_url,
            settings.odds_api_key,
        ).load(force=force)
        if not odds.empty:
            proj = proj.merge(odds, on="player_id", how="left")
            sources.append(_status("market_odds", True, f"{len(odds)} rows"))
        else:
            sources.append(
                _status(
                    "market_odds",
                    True,
                    "optional endpoint not configured",
                    configured=False,
                )
            )
    except Exception as exc:
        sources.append(_status("market_odds", False, str(exc), configured=True))

    proj = blend_projection(proj, settings.weights, settings.risk_penalty)
    decay = {gw: settings.fixture_decay**i for i, gw in enumerate(gws)}
    proj["decay"] = proj["gw"].map(decay)
    proj["weighted_xp"] = proj["risk_adjusted_xp"] * proj["decay"]
    summaries = _summarise_horizons(proj, gws)
    horizon_vals = proj.groupby("player_id", as_index=False).agg(
        horizon_xp=("weighted_xp", "sum")
    )
    first = proj[proj["gw"] == gws[0]][
        ["player_id", "risk_adjusted_xp"]
    ].rename(columns={"risk_adjusted_xp": "gw1_xp"})
    ranked = (
        players.merge(horizon_vals, on="player_id", how="left")
        .merge(first, on="player_id", how="left")
        .merge(summaries, on="player_id", how="left")
    )
    for col in [
        "horizon_xp",
        "gw1_xp",
        "xpts_1",
        "xpts_3",
        "xpts_5",
        "xpts_8",
        "projection_confidence",
    ]:
        ranked[col] = pd.to_numeric(
            ranked.get(col, 0),
            errors="coerce",
        ).fillna(0)

    scenarios = {}
    if scenario in {"unrestricted", "both"}:
        scenarios["unrestricted"] = optimise_squad(
            ranked,
            settings.budget,
            settings.max_per_team,
        )

    haaland_rows = ranked[
        ranked["web_name"].astype(str).str.casefold().eq("haaland")
    ]
    haaland_id = (
        int(haaland_rows.iloc[0]["player_id"])
        if not haaland_rows.empty
        else None
    )
    if scenario in {"haaland", "both"} and haaland_id is not None:
        scenarios["haaland"] = optimise_squad(
            ranked,
            settings.budget,
            settings.max_per_team,
            locked={haaland_id},
        )
    if scenario in {"no-haaland", "both"} and haaland_id is not None:
        scenarios["no-haaland"] = optimise_squad(
            ranked,
            settings.budget,
            settings.max_per_team,
            banned={haaland_id},
        )

    transfer_plan: TransferPlan | None = None
    if plan_transfers and team_resolution is not None and team_resolution.state is not None:
        team_state = team_resolution.state
        transfer_plan = optimise_transfer_plan(
            ranked,
            proj,
            gws,
            team_state.squad,
            bank=team_state.bank,
            free_transfers=team_state.free_transfers,
            max_per_team=settings.max_per_team,
            decay=settings.fixture_decay,
            selling_prices=team_state.selling_prices,
        )

    data_quality = assess_data_quality(
        official,
        core,
        friendlies,
        fx,
        proj,
        gws,
        fixture_fallback_ok=active_understat or elo_complete,
    )

    safety = assess_safety(
        official,
        sources,
        integrity,
        proj,
        scenarios,
        settings.required_sources,
        settings.max_official_age_hours,
        data_quality=data_quality,
    )

    ranked_cols = [
        "player_id",
        "web_name",
        "team_name",
        "position",
        "price",
        "status",
        "chance_of_playing_next_round",
        "expected_minutes",
        "start_probability",
        "appearance_probability",
        "minutes_60_plus_probability",
        "minutes_confidence",
        "tactical_role",
        "tactical_role_source",
        "role_multiplier",
        "role_confidence",
        "penalty_share",
        "corners_share",
        "direct_freekick_share",
        "indirect_freekick_share",
        "tactical_attack_index",
        "tactical_defence_index",
        "preseason_minutes",
        "preseason_starts",
        "preseason_xg90",
        "preseason_xa90",
        "gw1_xp",
        "xpts_1",
        "xpts_3",
        "xpts_5",
        "xpts_8",
        "horizon_xp",
        "projection_confidence",
    ]
    ranked_out = ranked[
        [col for col in ranked_cols if col in ranked]
    ].sort_values("horizon_xp", ascending=False)
    if not understat_ratings.empty:
        understat_ratings.to_csv(
            settings.report_dir / "team_goal_ratings.csv", index=False
        )
    if not understat_surface.empty:
        understat_surface.to_csv(
            settings.report_dir / "team_goal_surface.csv", index=False
        )
    write_reports(
        settings.report_dir,
        ranked_out,
        proj,
        integrity,
        news_audit,
        scenarios,
        transfer_plan,
        sources,
        gws,
        safety=safety,
        snapshot=manifest,
        upstreams=pins,
        data_quality=data_quality,
    )
    return PipelineOutput(
        ranked_out,
        proj,
        integrity,
        news_audit,
        scenarios,
        transfer_plan,
        sources,
        gws,
        safety,
        manifest,
        data_quality,
        team_resolution,
    )
