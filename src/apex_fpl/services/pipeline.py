from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json

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
from apex_fpl.services.decision_bundle import dataframe_sha256
from apex_fpl.services.enrichment import add_preseason_features, coalesce_context
from apex_fpl.services.integrity import reconcile
from apex_fpl.services.news_signals import infer_news_signals
from apex_fpl.services.provenance import SourceStatus, load_upstream_pins, validate_core_pin
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
    upstreams: dict = field(default_factory=dict)
    material_inputs: dict = field(default_factory=dict)


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


def _material_frame(frame: pd.DataFrame) -> dict[str, int | str]:
    return {
        "rows": int(len(frame)),
        "sha256": dataframe_sha256(frame),
    }


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


def _raw_projection_column(proj: pd.DataFrame) -> str:
    for column in ("canonical_ev_xp", "xp", "risk_adjusted_xp"):
        if column in proj.columns:
            return column
    raise ValueError("projection surface has no canonical expected-points column")


def _summarise_horizons(proj: pd.DataFrame, gws: list[int]) -> pd.DataFrame:
    """Expose xpts_N as undiscounted cumulative expected FPL points.

    Fixture decay is a decision-policy utility transform, not a points forecast.
    It must never be published under an xP label.
    """
    pids = proj[["player_id"]].drop_duplicates().copy()
    raw_col = _raw_projection_column(proj)
    for horizon in (1, 3, 5, 8):
        chosen = gws[: min(horizon, len(gws))]
        vals = (
            proj[proj["gw"].isin(chosen)]
            .groupby("player_id")[raw_col]
            .sum()
        )
        pids[f"xpts_{horizon}"] = pids["player_id"].map(vals).fillna(0)
    conf = proj.groupby("player_id")["projection_confidence"].mean()
    pids["projection_confidence"] = pids["player_id"].map(conf).fillna(0)
    return pids


def _horizon_totals(proj: pd.DataFrame) -> pd.DataFrame:
    raw_col = _raw_projection_column(proj)
    if "weighted_xp" not in proj.columns:
        raise ValueError("projection surface has no discounted utility component")
    out = proj.groupby("player_id", as_index=False).agg(
        raw_horizon_xp=(raw_col, "sum"),
        discounted_horizon_utility=("weighted_xp", "sum"),
    )
    # Compatibility alias: horizon_xp now has literal xP semantics. Any optimiser
    # that wants discounted utility must use discounted_horizon_utility explicitly.
    out["horizon_xp"] = out["raw_horizon_xp"]
    return out


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
            season=settings.season,
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
    core_ok, core_detail, core_runtime = validate_core_pin(
        pins.get("fpl_core_insights", {}),
        max_age_hours=settings.max_core_age_hours,
    )
    pins.setdefault("fpl_core_insights", {})["runtime_freshness"] = core_runtime
    air = pd.DataFrame()
    try:
        if not core_ok:
            raise RuntimeError(core_detail)
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
            collection = collect_news_sources(settings.news_sources or settings.news_feeds)
            headlines = collection.items
            now_utc = pd.Timestamp(datetime.now(timezone.utc))
            published = pd.to_datetime(
                pd.Series([item.published for item in headlines]), utc=True, errors="coerce"
            )
            fresh_items = int(
                (
                    published.notna()
                    & published.le(now_utc)
                    & ((now_utc - published).dt.total_seconds() / 3600 <= 120.0)
                ).sum()
            )
            source_health = {
                "configured_sources": len(settings.news_sources or settings.news_feeds),
                "healthy_sources": len(collection.succeeded),
                "fresh_timestamped_items": fresh_items,
                "failed_sources": sorted(collection.failed),
            }
            sources.append(
                _status(
                    "news_source_health",
                    True,
                    f"{len(collection.succeeded)} healthy; {fresh_items} fresh timestamped items",
                    version=json.dumps(source_health, sort_keys=True, separators=(",", ":")),
                )
            )
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
                    f"{len(headlines)} items; {len(news_audit)} player matches; "
                    f"{int(news_audit.get('eligible_for_projection', pd.Series(dtype=bool)).sum())} "
                    "projection-eligible evidence rows; "
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

    odds = pd.DataFrame()
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
    proj["discounted_horizon_utility_component"] = proj["weighted_xp"]
    summaries = _summarise_horizons(proj, gws)
    horizon_vals = _horizon_totals(proj)
    first = proj[proj["gw"] == gws[0]][
        ["player_id", "risk_adjusted_xp"]
    ].rename(columns={"risk_adjusted_xp": "gw1_xp"})
    ranked = (
        players.merge(horizon_vals, on="player_id", how="left")
        .merge(first, on="player_id", how="left")
        .merge(summaries, on="player_id", how="left")
    )
    ranked["fixture_decay"] = float(settings.fixture_decay)
    for col in [
        "raw_horizon_xp",
        "discounted_horizon_utility",
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
        "team",
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
        "historical_start_probability",
        "historical_expected_minutes",
        "preseason_start_probability",
        "preseason_average_minutes",
        "preseason_signal_minutes",
        "historical_signal_minutes",
        "role_expected_minutes_pre_availability",
        "role_start_probability_pre_availability",
        "availability_probability",
        "preseason_role_weight",
        "preseason_effective_games",
        "tactical_role",
        "tactical_role_source",
        "role_multiplier",
        "role_confidence",
        "lineup_evidence_type",
        "context_reason",
        "source_name",
        "source_tier",
        "source_url",
        "published_at",
        "retrieved_at",
        "expires_at",
        "availability_source_name",
        "availability_source_tier",
        "availability_source_url",
        "availability_evidence_type",
        "availability_published_at",
        "availability_retrieved_at",
        "availability_expires_at",
        "news_reason",
        "news_event_type",
        "news_source_name",
        "news_source_tier",
        "news_source_url",
        "news_published_at",
        "news_retrieved_at",
        "news_minutes_delta",
        "news_start_probability_delta",
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
        "preseason_goals90",
        "preseason_assists90",
        "preseason_shots90",
        "preseason_shots_on_target90",
        "preseason_chances_created90",
        "preseason_box_touches90",
        "preseason_xg_observed",
        "preseason_xa_observed",
        "preseason_goals_observed",
        "preseason_assists_observed",
        "preseason_shots_observed",
        "understat_player_matched",
        "understat_match_method",
        "gw1_xp",
        "xpts_1",
        "xpts_3",
        "xpts_5",
        "xpts_8",
        "raw_horizon_xp",
        "discounted_horizon_utility",
        "horizon_xp",
        "fixture_decay",
        "projection_confidence",
    ]
    ranked_out = ranked[
        [col for col in ranked_cols if col in ranked]
    ].sort_values("raw_horizon_xp", ascending=False)
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
    material_inputs = {
        "official_players": _material_frame(official.players),
        "official_fixtures": _material_frame(official.fixtures),
        "fpl_core_playerstats": _material_frame(core),
        "fpl_core_previous_season": _material_frame(previous),
        "fpl_core_preseason": _material_frame(friendlies),
        "fpl_core_elo": _material_frame(core_elos),
        "manual_availability": _material_frame(manual),
        "tactical_roles": _material_frame(tactical),
        "news_evidence": _material_frame(news_audit),
        "understat_team_ratings": _material_frame(understat_ratings),
        "understat_team_goal_surface": _material_frame(understat_surface),
        "fixture_projection_surface": _material_frame(fx),
        "airsenal_projection_surface": _material_frame(air),
        "market_odds_surface": _material_frame(odds),
        "final_projection_matrix": _material_frame(proj),
    }
    return PipelineOutput(
        players=ranked_out,
        projections=proj,
        integrity=integrity,
        news_audit=news_audit,
        scenarios=scenarios,
        transfer_plan=transfer_plan,
        sources=sources,
        gameweeks=gws,
        safety=safety,
        snapshot=manifest,
        data_quality=data_quality,
        team_state=team_resolution,
        upstreams=pins,
        material_inputs=material_inputs,
    )
