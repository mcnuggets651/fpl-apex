from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _load_env_file(path: str | Path = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _configured_news_feeds(raw: dict[str, Any]) -> list[str]:
    env = [x.strip() for x in os.getenv("APEX_NEWS_FEEDS", "").split(",") if x.strip()]
    if env:
        return env
    path = Path("config/news_sources.yaml")
    if not path.exists():
        return list(raw.get("news_feeds", []))
    cfg = yaml.safe_load(path.read_text()) or {}
    feeds = cfg.get("feeds", [])
    urls: list[str] = []
    for item in feeds:
        if isinstance(item, str):
            urls.append(item)
        elif isinstance(item, dict) and item.get("url"):
            urls.append(str(item["url"]))
    return urls


@dataclass
class Settings:
    season: str = "2026-2027"
    horizon: int = 8
    budget: float = 100.0
    max_per_team: int = 3
    fixture_decay: float = 0.90
    risk_penalty: float = 0.15
    weights: dict[str, float] = field(default_factory=lambda: {
        "official_ep": 0.24,
        "apex_model": 0.46,
        "airsenal": 0.20,
        "market": 0.10,
    })
    bench_weights: list[float] = field(default_factory=lambda: [0.15, 0.08, 0.04, 0.02])
    cache_dir: Path = Path("data/cache")
    snapshot_dir: Path = Path("data/snapshots")
    report_dir: Path = Path("reports")
    airsenal_csv: str | None = "data/generated/airsenal.csv"
    odds_api_key: str | None = None
    odds_api_url: str | None = None
    news_feeds: list[str] = field(default_factory=list)
    current_squad_path: Path = Path("data/manual/current_squad.csv")
    team_state_path: Path = Path("data/manual/team_state.yaml")
    tactical_roles_path: Path = Path("data/manual/tactical_roles.csv")
    upstreams_lock_path: Path = Path("upstreams.lock.json")
    required_sources: list[str] = field(default_factory=lambda: [
        "official_fpl", "fpl_core_playerstats", "airsenal", "news_feeds"
    ])
    max_official_age_hours: float = 26.0
    max_airsenal_age_hours: float = 36.0
    min_airsenal_player_coverage: float = 0.45


def load_settings(path: str | Path = "config/apex.yaml") -> Settings:
    _load_env_file()
    raw: dict[str, Any] = {}
    p = Path(path)
    if p.exists():
        raw = yaml.safe_load(p.read_text()) or {}
    default = Settings()
    s = Settings(
        season=os.getenv("APEX_SEASON", raw.get("season", default.season)),
        horizon=int(os.getenv("APEX_HORIZON", raw.get("horizon", default.horizon))),
        budget=float(os.getenv("APEX_BUDGET", raw.get("budget", default.budget))),
        max_per_team=int(raw.get("max_per_team", default.max_per_team)),
        fixture_decay=float(raw.get("fixture_decay", default.fixture_decay)),
        risk_penalty=float(raw.get("risk_penalty", default.risk_penalty)),
        weights=raw.get("weights", default.weights),
        bench_weights=raw.get("bench_weights", default.bench_weights),
        cache_dir=Path(os.getenv("APEX_CACHE_DIR", "data/cache")),
        snapshot_dir=Path(os.getenv("APEX_SNAPSHOT_DIR", "data/snapshots")),
        report_dir=Path(os.getenv("APEX_REPORT_DIR", "reports")),
        airsenal_csv=(
            os.getenv(
                "AIRSENAL_PROJECTIONS_CSV",
                str(raw.get("airsenal_csv", default.airsenal_csv or "")),
            )
            or None
        ),
        odds_api_key=os.getenv("ODDS_API_KEY") or None,
        odds_api_url=os.getenv("ODDS_API_URL") or None,
        news_feeds=_configured_news_feeds(raw),
        current_squad_path=Path(os.getenv("APEX_CURRENT_SQUAD", "data/manual/current_squad.csv")),
        team_state_path=Path(os.getenv("APEX_TEAM_STATE", "data/manual/team_state.yaml")),
        tactical_roles_path=Path(os.getenv("APEX_TACTICAL_ROLES", "data/manual/tactical_roles.csv")),
        upstreams_lock_path=Path(os.getenv("APEX_UPSTREAMS_LOCK", "upstreams.lock.json")),
        required_sources=list(raw.get("required_sources", default.required_sources)),
        max_official_age_hours=float(
            raw.get("max_official_age_hours", default.max_official_age_hours)
        ),
        max_airsenal_age_hours=float(
            raw.get("max_airsenal_age_hours", default.max_airsenal_age_hours)
        ),
        min_airsenal_player_coverage=float(
            raw.get("min_airsenal_player_coverage", default.min_airsenal_player_coverage)
        ),
    )
    s.cache_dir.mkdir(parents=True, exist_ok=True)
    s.snapshot_dir.mkdir(parents=True, exist_ok=True)
    s.report_dir.mkdir(parents=True, exist_ok=True)
    return s
