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


def _configured_news_sources(raw: dict[str, Any]) -> list[dict[str, str]]:
    env = [x.strip() for x in os.getenv("APEX_NEWS_FEEDS", "").split(",") if x.strip()]
    if env:
        return [
            {"name": value, "url": value, "tier": "unknown"}
            for value in env
        ]
    path = Path("config/news_sources.yaml")
    if not path.exists():
        return [
            {"name": str(value), "url": str(value), "tier": "unknown"}
            for value in raw.get("news_feeds", [])
        ]
    cfg = yaml.safe_load(path.read_text()) or {}
    feeds = cfg.get("feeds", [])
    sources: list[dict[str, str]] = []
    for item in feeds:
        if isinstance(item, str):
            sources.append({"name": item, "url": item, "tier": "unknown"})
        elif isinstance(item, dict) and item.get("url"):
            sources.append(
                {
                    "name": str(item.get("name") or item["url"]),
                    "url": str(item["url"]),
                    "tier": str(item.get("tier") or "unknown"),
                }
            )
    return sources


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    parsed = int(text)
    if parsed <= 0:
        raise ValueError("FPL entry ID must be a positive integer")
    return parsed


def _validated_weights(raw: dict[str, Any]) -> dict[str, float]:
    expected = {"official_ep", "apex_model", "airsenal", "market"}
    unknown = set(raw) - expected
    if unknown:
        raise ValueError(f"unknown ensemble weight keys: {sorted(unknown)}")
    weights = {key: float(raw.get(key, 0.0)) for key in expected}
    if any(value < 0 for value in weights.values()):
        raise ValueError("ensemble weights must be non-negative")
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(
            f"production ensemble weights must sum to 1.0 exactly; got {total:.12f}"
        )
    return weights


@dataclass
class Settings:
    season: str = "2026-2027"
    horizon: int = 8
    budget: float = 100.0
    max_per_team: int = 3
    fixture_decay: float = 0.90
    risk_penalty: float = 0.15
    # Production statistical authority is intentionally one-hot until a challenger
    # passes genuine prospective promotion. These are authority weights, not a hand-tuned blend.
    weights: dict[str, float] = field(default_factory=lambda: {
        "official_ep": 0.0,
        "apex_model": 0.0,
        "airsenal": 1.0,
        "market": 0.0,
    })
    approximate_bench_weight: float = 0.08
    exact_candidate_limit: int = 16
    exact_candidate_regret_fraction: float = 0.005
    exact_near_equivalent_points: float = 0.25
    cache_dir: Path = Path("data/cache")
    snapshot_dir: Path = Path("data/snapshots")
    report_dir: Path = Path("reports")
    airsenal_csv: str | None = "data/generated/airsenal.csv"
    odds_api_key: str | None = None
    odds_api_url: str | None = None
    news_feeds: list[str] = field(default_factory=list)
    news_sources: list[dict[str, str]] = field(default_factory=list)
    fpl_entry_id: int | None = None
    current_squad_path: Path = Path("data/manual/current_squad.csv")
    team_state_path: Path = Path("data/manual/team_state.yaml")
    tactical_roles_path: Path = Path("data/manual/tactical_roles.csv")
    upstreams_lock_path: Path = Path("upstreams.lock.json")
    required_sources: list[str] = field(default_factory=lambda: [
        "official_fpl",
        "airsenal",
        "news_feeds",
    ])
    max_official_age_hours: float = 26.0
    max_airsenal_age_hours: float = 36.0
    max_core_age_hours: float = 18.0
    min_airsenal_player_coverage: float = 1.0
    understat_enabled: bool = True
    understat_history_seasons: int = 5
    understat_team_model_mode: str = "shadow"


def load_settings(path: str | Path = "config/apex.yaml") -> Settings:
    _load_env_file()
    raw: dict[str, Any] = {}
    p = Path(path)
    if p.exists():
        raw = yaml.safe_load(p.read_text()) or {}
    default = Settings()
    news_sources = _configured_news_sources(raw)
    configured_weights = _validated_weights(dict(raw.get("weights", default.weights)))
    odds_api_url = os.getenv("ODDS_API_URL") or None
    odds_api_key = os.getenv("ODDS_API_KEY") or None
    if configured_weights.get("market", 0.0) > 0 and not odds_api_url:
        raise ValueError(
            "positive market ensemble weight requires ODDS_API_URL; "
            "keep market weight at zero while market xP is unavailable"
        )
    s = Settings(
        season=os.getenv("APEX_SEASON", raw.get("season", default.season)),
        horizon=int(os.getenv("APEX_HORIZON", raw.get("horizon", default.horizon))),
        budget=float(os.getenv("APEX_BUDGET", raw.get("budget", default.budget))),
        max_per_team=int(raw.get("max_per_team", default.max_per_team)),
        fixture_decay=float(raw.get("fixture_decay", default.fixture_decay)),
        risk_penalty=float(raw.get("risk_penalty", default.risk_penalty)),
        weights=configured_weights,
        approximate_bench_weight=float(
            raw.get("approximate_bench_weight", default.approximate_bench_weight)
        ),
        exact_candidate_limit=int(
            raw.get("exact_candidate_limit", default.exact_candidate_limit)
        ),
        exact_candidate_regret_fraction=float(
            raw.get(
                "exact_candidate_regret_fraction",
                default.exact_candidate_regret_fraction,
            )
        ),
        exact_near_equivalent_points=float(
            raw.get(
                "exact_near_equivalent_points",
                default.exact_near_equivalent_points,
            )
        ),
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
        odds_api_key=odds_api_key,
        odds_api_url=odds_api_url,
        news_feeds=[row["url"] for row in news_sources],
        news_sources=news_sources,
        fpl_entry_id=_optional_int(
            os.getenv("FPL_ENTRY_ID", raw.get("fpl_entry_id", default.fpl_entry_id))
        ),
        current_squad_path=Path(
            os.getenv("APEX_CURRENT_SQUAD", "data/manual/current_squad.csv")
        ),
        team_state_path=Path(
            os.getenv("APEX_TEAM_STATE", "data/manual/team_state.yaml")
        ),
        tactical_roles_path=Path(
            os.getenv("APEX_TACTICAL_ROLES", "data/manual/tactical_roles.csv")
        ),
        upstreams_lock_path=Path(
            os.getenv("APEX_UPSTREAMS_LOCK", "upstreams.lock.json")
        ),
        required_sources=list(raw.get("required_sources", default.required_sources)),
        max_official_age_hours=float(
            raw.get("max_official_age_hours", default.max_official_age_hours)
        ),
        max_airsenal_age_hours=float(
            raw.get("max_airsenal_age_hours", default.max_airsenal_age_hours)
        ),
        max_core_age_hours=float(
            os.getenv(
                "APEX_MAX_CORE_AGE_HOURS",
                raw.get("max_core_age_hours", default.max_core_age_hours),
            )
        ),
        min_airsenal_player_coverage=float(
            raw.get("min_airsenal_player_coverage", default.min_airsenal_player_coverage)
        ),
        understat_enabled=str(
            os.getenv("APEX_UNDERSTAT_ENABLED", raw.get("understat_enabled", True))
        ).strip().casefold()
        not in {"0", "false", "no", "off"},
        understat_history_seasons=int(
            raw.get("understat_history_seasons", default.understat_history_seasons)
        ),
        understat_team_model_mode=str(
            os.getenv(
                "APEX_UNDERSTAT_TEAM_MODEL_MODE",
                raw.get(
                    "understat_team_model_mode",
                    default.understat_team_model_mode,
                ),
            )
        ).strip().casefold(),
    )
    if s.understat_team_model_mode not in {"shadow", "production"}:
        raise ValueError(
            "understat_team_model_mode must be 'shadow' or 'production'"
        )
    s.cache_dir.mkdir(parents=True, exist_ok=True)
    s.snapshot_dir.mkdir(parents=True, exist_ok=True)
    s.report_dir.mkdir(parents=True, exist_ok=True)
    return s
