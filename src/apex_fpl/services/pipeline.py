from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd

from apex_fpl.config import Settings
from apex_fpl.data.airsenal import AIrsenalProjectionAdapter, validate_airsenal_forecast
from apex_fpl.data.core_insights import FPLCoreClient
from apex_fpl.data.http import CachedHttp
from apex_fpl.data.news import collect_feed_headlines, load_manual_signals
from apex_fpl.data.odds import OddsAdapter
from apex_fpl.data.official import OfficialFPLClient
from apex_fpl.data.tactical import load_tactical_roles
from apex_fpl.models.ensemble import blend_projection
from apex_fpl.models.fixtures import fixture_multipliers, next_gameweeks
from apex_fpl.models.minutes import minutes_profile
from apex_fpl.models.projection import project_players
from apex_fpl.optimisation.squad import optimise_squad
from apex_fpl.optimisation.transfers import TransferPlan, optimise_transfer_plan
from apex_fpl.reporting.writer import write_reports
from apex_fpl.services.enrichment import add_preseason_features, coalesce_context
from apex_fpl.services.integrity import reconcile
from apex_fpl.services.news_signals import infer_news_signals
from apex_fpl.services.provenance import SourceStatus, load_upstream_pins
from apex_fpl.services.safety import SafetyAssessment, assess_safety
from apex_fpl.services.snapshots import write_official_snapshot
from apex_fpl.services.team_state import load_team_state


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


def _official_ep(players: pd.DataFrame, gameweeks: list[int]) -> pd.DataFrame:
    if not gameweeks:
        return pd.DataFrame(columns=["player_id", "gw", "official_xp"])
    ep = pd.to_numeric(players.get("ep_next", np.nan), errors="coerce")
    return pd.DataFrame({"player_id": players["player_id"], "gw": gameweeks[0], "official_xp": ep})


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


def _summarise_horizons(proj: pd.DataFrame, gws: list[int]) -> pd.DataFrame:
    pids = proj[["player_id"]].drop_duplicates().copy()
    for horizon in (1, 3, 5, 8):
        chosen = gws[: min(horizon, len(gws))]
        vals = proj[proj["gw"].isin(chosen)].groupby("player_id")["weighted_xp"].sum()
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

    core = pd.DataFrame(columns=["player_id"])
    friendlies = pd.DataFrame()
    core_pin = str(pins.get("fpl_core_insights", {}).get("commit", ""))
    try:
        core_client = FPLCoreClient(http, settings.season, ref=core_pin or "main")
        core = core_client.playerstats(force=force)
        sources.append(
            _status("fpl_core_playerstats", True, f"{len(core)} rows", version=core_pin)
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
            sources.append(_status("fpl_core_preseason", False, str(exc), version=core_pin))
    except Exception as exc:
        sources.append(_status("fpl_core_playerstats", False, str(exc), version=core_pin))

    players, integrity = reconcile(official.players, core)
    players = coalesce_context(players)
    players = add_preseason_features(players, friendlies)

    manual = load_manual_signals()
    if not manual.empty:
        players = players.merge(manual, on="player_id", how="left")
        sources.append(_status("manual_availability", True, f"{len(manual)} rows"))
    else:
        sources.append(
            _status("manual_availability", True, "not configured", configured=False)
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
            _status("tactical_roles", True, f"{len(tactical)} verified role overrides")
        )
    else:
        sources.append(
            _status("tactical_roles", True, "no verified overrides", configured=False)
        )
    role_mult = (
        players["role_multiplier"]
        if "role_multiplier" in players
        else pd.Series(1.0, index=players.index)
    )
    role_conf = (
        players["role_confidence"]
        if "role_confidence" in players
        else pd.Series(0.65, index=players.index)
    )
    players["role_multiplier"] = pd.to_numeric(role_mult, errors="coerce").fillna(1.0)
    players["role_confidence"] = pd.to_numeric(role_conf, errors="coerce").fillna(0.65)

    news_audit = pd.DataFrame()
    if settings.news_feeds:
        try:
            headlines = collect_feed_headlines(settings.news_feeds)
            news_signal, news_audit = infer_news_signals(players, headlines)
            if not news_signal.empty:
                players = players.merge(news_signal, on="player_id", how="left")
            sources.append(
                _status(
                    "news_feeds",
                    True,
                    f"{len(headlines)} headlines; {len(news_audit)} player matches",
                )
            )
        except Exception as exc:
            sources.append(_status("news_feeds", False, str(exc), configured=True))
    else:
        sources.append(_status("news_feeds", True, "not configured", configured=False))

    profile = minutes_profile(players)
    for col in profile.columns:
        players[col] = profile[col]

    gws = next_gameweeks(official.events, horizon)
    if not gws:
        raise RuntimeError("Official FPL API returned no future gameweeks")
    fx = fixture_multipliers(official.fixtures, official.teams, gws)
    apex = project_players(players, fx, gws)
    projection_context = players[["player_id", "minutes_confidence", "role_confidence"]]
    proj = apex.merge(projection_context, on="player_id", how="left").merge(
        _official_ep(players, gws), on=["player_id", "gw"], how="left"
    )

    # Genuine AIrsenal is an independent expert, but it is only allowed into the
    # ensemble when official-ID, pinned-version, freshness and horizon checks pass.
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
        odds = OddsAdapter(http, settings.odds_api_url, settings.odds_api_key).load(force=force)
        if not odds.empty:
            proj = proj.merge(odds, on="player_id", how="left")
            sources.append(_status("market_odds", True, f"{len(odds)} rows"))
        else:
            sources.append(
                _status("market_odds", True, "optional endpoint not configured", configured=False)
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
    first = proj[proj["gw"] == gws[0]][["player_id", "risk_adjusted_xp"]].rename(
        columns={"risk_adjusted_xp": "gw1_xp"}
    )
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
        ranked[col] = pd.to_numeric(ranked.get(col, 0), errors="coerce").fillna(0)

    scenarios = {}
    if scenario in {"unrestricted", "both"}:
        scenarios["unrestricted"] = optimise_squad(
            ranked, settings.budget, settings.max_per_team
        )

    haaland_rows = ranked[
        ranked["web_name"].astype(str).str.casefold().eq("haaland")
    ]
    haaland_id = int(haaland_rows.iloc[0]["player_id"]) if not haaland_rows.empty else None
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
    if plan_transfers:
        team_state = load_team_state(settings.current_squad_path, settings.team_state_path)
        if team_state is not None:
            transfer_plan = optimise_transfer_plan(
                ranked,
                proj,
                gws,
                team_state.squad,
                bank=team_state.bank,
                free_transfers=team_state.free_transfers,
                max_per_team=settings.max_per_team,
                decay=settings.fixture_decay,
            )
            sources.append(_status("team_state", True, "manual current squad loaded"))
        else:
            sources.append(
                _status(
                    "team_state",
                    True,
                    "not configured; initial-squad mode",
                    configured=False,
                )
            )

    safety = assess_safety(
        official,
        sources,
        integrity,
        proj,
        scenarios,
        settings.required_sources,
        settings.max_official_age_hours,
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
        "role_confidence",
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
        [c for c in ranked_cols if c in ranked]
    ].sort_values("horizon_xp", ascending=False)
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
    )
