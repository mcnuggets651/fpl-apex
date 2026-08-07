from __future__ import annotations

from dataclasses import dataclass
import gzip
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Callable, Iterable
import urllib.error
import urllib.request
import warnings
import zlib

import pandas as pd

from apex_fpl.data.team_mapping import canonical_team


UNDERSTAT_API_URL = "https://understat.com/getLeagueData/EPL/{season}/"
UNDERSTAT_PAGE_URL = "https://understat.com/league/EPL/{season}"


class UnderstatDataError(RuntimeError):
    """Raised when genuine Understat history is unavailable or invalid."""


@dataclass(frozen=True)
class UnderstatHistory:
    matches: pd.DataFrame
    completed_seasons: tuple[int, ...]
    active_season_loaded: bool
    warnings: tuple[str, ...]


def season_start_year(season: str | int) -> int:
    if isinstance(season, int):
        return season
    match = re.search(r"(20\d{2}|19\d{2})", str(season))
    if not match:
        raise ValueError(f"Unsupported season value: {season!r}")
    return int(match.group(1))


def decode_league_payload(payload: str | bytes | dict) -> dict:
    try:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        data = json.loads(payload) if isinstance(payload, str) else payload
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UnderstatDataError(f"Understat response is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise UnderstatDataError("Understat league payload is not an object")
    if not isinstance(data.get("dates"), list):
        raise UnderstatDataError("Understat league payload has no dates list")
    if not isinstance(data.get("teams"), dict):
        raise UnderstatDataError("Understat league payload has no teams object")
    return data


def _default_fetch(url: str, timeout: int) -> str:
    season = url.rstrip("/").rsplit("/", 1)[-1]
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; apex-fpl/0.1)",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Encoding": "gzip, deflate",
            "Referer": UNDERSTAT_PAGE_URL.format(season=season),
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            encoding = (response.headers.get("Content-Encoding") or "").lower()
            if "gzip" in encoding or body.startswith(b"\x1f\x8b"):
                body = gzip.decompress(body)
            elif "deflate" in encoding:
                body = zlib.decompress(body)
            charset = response.headers.get_content_charset() or "utf-8"
            return body.decode(charset)
    except urllib.error.HTTPError as exc:
        snippet = exc.read(240).decode("utf-8", errors="replace").replace("\n", " ")
        raise UnderstatDataError(f"HTTP {exc.code} from {url}: {snippet[:200]}") from exc
    except urllib.error.URLError as exc:
        raise UnderstatDataError(f"Network error from {url}: {exc.reason}") from exc


def _cache_file(cache_dir: Path, season: int) -> Path:
    key = hashlib.sha256(UNDERSTAT_API_URL.format(season=season).encode()).hexdigest()[:12]
    return cache_dir / f"epl_{season}_{key}.json"


def _read_cache(path: Path) -> dict:
    try:
        return decode_league_payload(path.read_text(encoding="utf-8"))
    except (OSError, UnderstatDataError) as exc:
        raise UnderstatDataError(f"Invalid Understat cache {path}: {exc}") from exc


def fetch_understat_season(
    season: str | int,
    *,
    cache_dir: str | Path,
    timeout: int = 20,
    attempts: int = 3,
    refresh: bool = False,
    fetcher: Callable[[str, int], str] = _default_fetch,
) -> dict:
    """Fetch one season with validation, atomic caching and stale fallback."""
    year = season_start_year(season)
    cache_path = _cache_file(Path(cache_dir), year)
    if cache_path.exists() and not refresh:
        return _read_cache(cache_path)

    errors: list[str] = []
    for attempt in range(1, max(attempts, 1) + 1):
        try:
            payload = decode_league_payload(
                fetcher(UNDERSTAT_API_URL.format(season=year), timeout)
            )
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = cache_path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            temporary.replace(cache_path)
            return payload
        except Exception as exc:
            errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
            if attempt < max(attempts, 1):
                time.sleep(0.5 * (2 ** (attempt - 1)))

    if cache_path.exists():
        warnings.warn(
            f"Understat EPL {year} refresh failed; using validated stale cache ({errors[-1]})",
            RuntimeWarning,
        )
        return _read_cache(cache_path)
    raise UnderstatDataError(
        f"Understat EPL {year} unavailable after {attempts} attempts; " + " | ".join(errors)
    )


def _normalise_matches(payload: dict, season: int) -> pd.DataFrame:
    records: list[dict] = []
    for row in payload["dates"]:
        if not row.get("isResult"):
            continue
        home, away = row.get("h") or {}, row.get("a") or {}
        xg, goals = row.get("xG") or {}, row.get("goals") or {}
        records.append(
            {
                "understat_match_id": row.get("id"),
                "date": row.get("datetime"),
                "season": int(season),
                "team_home": canonical_team(home.get("title")),
                "team_away": canonical_team(away.get("title")),
                "goals_home": goals.get("h"),
                "goals_away": goals.get("a"),
                "xg_home": xg.get("h"),
                "xg_away": xg.get("a"),
            }
        )
    columns = [
        "understat_match_id",
        "date",
        "season",
        "team_home",
        "team_away",
        "goals_home",
        "goals_away",
        "xg_home",
        "xg_away",
    ]
    frame = pd.DataFrame.from_records(records, columns=columns)
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    for column in ("goals_home", "goals_away", "xg_home", "xg_away"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    required = ["date", "team_home", "team_away", "xg_home", "xg_away"]
    if frame[required].isna().any().any():
        bad = int(frame[required].isna().any(axis=1).sum())
        raise UnderstatDataError(f"Understat EPL {season} has {bad} invalid completed matches")
    if frame.duplicated(["date", "team_home", "team_away"]).any():
        raise UnderstatDataError(f"Understat EPL {season} contains duplicate matches")
    return frame.sort_values(["date", "understat_match_id"]).reset_index(drop=True)


def load_understat_history(
    seasons: Iterable[str | int],
    *,
    active_season: str | int,
    cache_dir: str | Path,
    refresh_active: bool = True,
) -> UnderstatHistory:
    requested = sorted({season_start_year(season) for season in seasons})
    active = season_start_year(active_season)
    frames: list[pd.DataFrame] = []
    completed: list[int] = []
    notes: list[str] = []
    active_loaded = False

    for year in requested:
        try:
            payload = fetch_understat_season(
                year,
                cache_dir=cache_dir,
                refresh=refresh_active and year == active,
            )
            frame = _normalise_matches(payload, year)
        except Exception as exc:
            if year == active:
                notes.append(f"active season {year} unavailable: {type(exc).__name__}: {exc}")
                continue
            raise UnderstatDataError(
                f"completed season {year} unavailable: {type(exc).__name__}: {exc}"
            ) from exc
        if year < active:
            if len(frame) != 380:
                raise UnderstatDataError(
                    f"completed EPL season {year} returned {len(frame)} matches; expected 380"
                )
            completed.append(year)
        else:
            active_loaded = True
        if not frame.empty:
            frames.append(frame)

    if not completed:
        raise UnderstatDataError("no complete historical EPL season was loaded")
    result = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()
    if result.duplicated(["date", "team_home", "team_away"]).any():
        raise UnderstatDataError("duplicate fixtures found across Understat seasons")
    return UnderstatHistory(
        result.sort_values("date").reset_index(drop=True),
        tuple(completed),
        active_loaded,
        tuple(notes),
    )
