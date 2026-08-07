from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd

from apex_fpl.config import Settings
from apex_fpl.data.airsenal import AIrsenalProjectionAdapter
from apex_fpl.data.core_insights import FPLCoreClient
from apex_fpl.data.context import load_player_context
from apex_fpl.data.http import CachedHttp
from apex_fpl.data.news import collect_feed_headlines, load_manual_signals
from apex_fpl.data.odds import OddsAdapter
from apex_fpl.data.official import OfficialFPLClient
from apex_fpl.models.ensemble import blend_projection
from apex_fpl.models.fixtures import fixture_multipliers, next_gameweeks
from apex_fpl.models.minutes import expected_minutes
from apex_fpl.models.projection import project_players
from apex_fpl.optimisation.squad import optimise_squad
from apex_fpl.optimisation.transfers import TransferPlan, optimise_transfer_plan
from apex_fpl.reporting.writer import write_reports
from apex_fpl.services.enrichment import add_preseason_features, coalesce_context
from apex_fpl.services.integrity import reconcile
from apex_fpl.services.news_signals import infer_news_signals
from apex_fpl.services.provenance import SourceStatus
from apex_fpl.services.team_state import load_team_state
from apex_fpl.services.source_gate import SafetyGate, evaluate_source_gate


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
    safety: SafetyGate


def _official_ep(players: pd.DataFrame, gameweeks: list[int]) -> pd.DataFrame:
    if not gameweeks:
        return pd.DataFrame(columns=["player_id", "gw", "official_xp"])
    # FPL only exposes ep_next for the immediate next GW; keep it to that GW.
    ep = pd.to_numeric(players.get("ep_next", np.nan), errors="coerce")
    return pd.DataFrame({"player_id": players["player_id"], "gw": gameweeks[0], "official_xp": ep})


def _status(name: str, ok: bool, detail: str = "") -> SourceStatus:
    return SourceStatus(name=name, ok=ok, detail=detail)


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

    # Canonical source: fail loudly if this is unavailable. A stale/partial
    # recommendation is more dangerous than no recommendation.
    official = OfficialFPLClient(http).snapshot(force=force)
    sources.append(_status("official_fpl", True, f"{len(official.players)} players; {len(official.fixtures)} fixtures"))

    core = pd.DataFrame(columns=["player_id"])
    friendlies = pd.DataFrame()
    try:
        core_client = FPLCoreClient(http, settings.season)
        core = core_client.playerstats(force=force)
        sources.append(_status("fpl_core_playerstats", True, f"{len(core)} rows"))
        try:
            friendlies = core_client.preseason_friendlies(force=force)
            sources.append(_status("fpl_core_preseason", True, f"{len(friendlies)} player-match rows"))
        except Exception as exc:
            sources.append(_status("fpl_core_preseason", False, str(exc)))
    except Exception as exc:
        sources.append(_status("fpl_core_playerstats", False, str(exc)))

    players, integrity = reconcile(official.players, core)
    players = coalesce_context(players)
    players = add_preseason_features(players, friendlies)

    context = load_player_context(settings.player_context_path)
    if not context.empty:
        players = players.merge(context, on="player_id", how="left")
        sources.append(_status("verified_player_context", True, f"{len(context)} rows"))
    else:
        sources.append(_status("verified_player_context", True, "not configured"))

    # Official/manual/news availability layer. Manual is highest-priority user
    # override; headline inference is advisory and auditable.
    manual = load_manual_signals()
    if not manual.empty:
        players = players.merge(manual, on="player_id", how="left")
        sources.append(_status("manual_availability", True, f"{len(manual)} rows"))
    else:
        sources.append(_status("manual_availability", True, "not configured"))

    news_audit = pd.DataFrame()
    if settings.news_feeds:
        try:
            headlines = collect_feed_headlines(settings.news_feeds)
            news_signal, news_audit = infer_news_signals(players, headlines)
            if not news_signal.empty:
                players = players.merge(news_signal, on="player_id", how="left")
            sources.append(_status("news_feeds", True, f"{len(headlines)} headlines; {len(news_audit)} player matches"))
        except Exception as exc:
            sources.append(_status("news_feeds", False, str(exc)))
    else:
        sources.append(_status("news_feeds", True, "not configured"))
    players["expected_minutes"] = expected_minutes(players)

    gws = next_gameweeks(official.events, horizon)
    if not gws:
        raise RuntimeError("Official FPL API returned no future gameweeks")
    fx = fixture_multipliers(official.fixtures, official.teams, gws)
    apex = project_players(players, fx, gws)
    proj = apex.merge(_official_ep(players, gws), on=["player_id", "gw"], how="left")

    air_adapter = AIrsenalProjectionAdapter(settings.airsenal_csv)
    try:
        air = air_adapter.load()
        if not air.empty:
            proj = proj.merge(air, on=["player_id", "gw"], how="left")
            sources.append(_status("airsenal", True, f"{len(air)} projection rows"))
        else:
            sources.append(_status("airsenal", True, "optional projection export not configured"))
    except Exception as exc:
        sources.append(_status("airsenal", False, str(exc)))

    try:
        odds = OddsAdapter(http, settings.odds_api_url, settings.odds_api_key).load(force=force)
        if not odds.empty:
            proj = proj.merge(odds, on="player_id", how="left")
            sources.append(_status("market_odds", True, f"{len(odds)} rows"))
        else:
            sources.append(_status("market_odds", True, "optional endpoint not configured"))
    except Exception as exc:
        sources.append(_status("market_odds", False, str(exc)))

    proj = blend_projection(proj, settings.weights, settings.risk_penalty)
    decay = {gw: settings.fixture_decay ** i for i, gw in enumerate(gws)}
    proj["decay"] = proj["gw"].map(decay)
    proj["weighted_xp"] = proj["risk_adjusted_xp"] * proj["decay"]
    summary = proj.groupby("player_id", as_index=False).agg(horizon_xp=("weighted_xp", "sum"))
    first = proj[proj["gw"] == gws[0]][["player_id", "risk_adjusted_xp"]].rename(
        columns={"risk_adjusted_xp": "gw1_xp"}
    )
    ranked = players.merge(summary, on="player_id", how="left").merge(first, on="player_id", how="left")
    ranked["horizon_xp"] = ranked["horizon_xp"].fillna(0)
    ranked["gw1_xp"] = ranked["gw1_xp"].fillna(0)

    scenarios = {}
    if scenario in {"unrestricted", "both"}:
        scenarios["unrestricted"] = optimise_squad(ranked, settings.budget, settings.max_per_team)

    haaland_rows = ranked[ranked["web_name"].astype(str).str.casefold().eq("haaland")]
    haaland_id = int(haaland_rows.iloc[0]["player_id"]) if not haaland_rows.empty else None
    if scenario in {"haaland", "both"} and haaland_id is not None:
        scenarios["haaland"] = optimise_squad(
            ranked, settings.budget, settings.max_per_team, locked={haaland_id}
        )
    if scenario in {"no-haaland", "both"} and haaland_id is not None:
        scenarios["no-haaland"] = optimise_squad(
            ranked, settings.budget, settings.max_per_team, banned={haaland_id}
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
            sources.append(_status("team_state", True, "not configured; initial-squad mode"))

    ranked_cols = [
        "player_id", "web_name", "team_name", "position", "price", "status",
        "chance_of_playing_next_round", "expected_minutes", "preseason_minutes",
        "preseason_starts", "preseason_xg90", "preseason_xa90", "gw1_xp", "horizon_xp",
    ]
    ranked_out = ranked[[c for c in ranked_cols if c in ranked]].sort_values("horizon_xp", ascending=False)
    safety = evaluate_source_gate(
        sources,
        len(integrity),
        require_airsenal=settings.strict_apex and settings.require_airsenal,
        require_core=settings.strict_apex and settings.require_core,
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
        safety,
    )
    return PipelineOutput(ranked_out, proj, integrity, news_audit, scenarios, transfer_plan, sources, gws, safety)
