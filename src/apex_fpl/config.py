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
        os.environ.setdefault(key.strip(), value.strip().strip("\"\'"))


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
    horizon: int = 6
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
    report_dir: Path = Path("reports")
    airsenal_csv: str | None = None
    odds_api_key: str | None = None
    odds_api_url: str | None = None
    news_feeds: list[str] = field(default_factory=list)
    current_squad_path: Path = Path("data/manual/current_squad.csv")
    team_state_path: Path = Path("data/manual/team_state.yaml")
    player_context_path: Path = Path("data/manual/player_context.csv")
    strict_apex: bool = True
    require_airsenal: bool = True
    require_core: bool = True


def load_settings(path: str | Path = "config/apex.yaml") -> Settings:
    _load_env_file()
    raw: dict[str, Any] = {}
    p = Path(path)
    if p.exists():
        raw = yaml.safe_load(p.read_text()) or {}
    s = Settings(
        season=os.getenv("APEX_SEASON", raw.get("season", "2026-2027")),
        horizon=int(os.getenv("APEX_HORIZON", raw.get("horizon", 6))),
        budget=float(os.getenv("APEX_BUDGET", raw.get("budget", 100.0))),
        max_per_team=int(raw.get("max_per_team", 3)),
        fixture_decay=float(raw.get("fixture_decay", 0.90)),
        risk_penalty=float(raw.get("risk_penalty", 0.15)),
        weights=raw.get("weights", Settings().weights),
        bench_weights=raw.get("bench_weights", Settings().bench_weights),
        cache_dir=Path(os.getenv("APEX_CACHE_DIR", "data/cache")),
        report_dir=Path(os.getenv("APEX_REPORT_DIR", "reports")),
        airsenal_csv=os.getenv("AIRSENAL_PROJECTIONS_CSV") or None,
        odds_api_key=os.getenv("ODDS_API_KEY") or None,
        odds_api_url=os.getenv("ODDS_API_URL") or None,
        news_feeds=_configured_news_feeds(raw),
        current_squad_path=Path(os.getenv("APEX_CURRENT_SQUAD", "data/manual/current_squad.csv")),
        team_state_path=Path(os.getenv("APEX_TEAM_STATE", "data/manual/team_state.yaml")),
        player_context_path=Path(os.getenv("APEX_PLAYER_CONTEXT", "data/manual/player_context.csv")),
        strict_apex=str(os.getenv("APEX_STRICT", raw.get("strict_apex", True))).lower() not in {"0", "false", "no"},
        require_airsenal=str(os.getenv("APEX_REQUIRE_AIRSENAL", raw.get("require_airsenal", True))).lower() not in {"0", "false", "no"},
        require_core=str(os.getenv("APEX_REQUIRE_CORE", raw.get("require_core", True))).lower() not in {"0", "false", "no"},
    )
    s.cache_dir.mkdir(parents=True, exist_ok=True)
    s.report_dir.mkdir(parents=True, exist_ok=True)
    return s
