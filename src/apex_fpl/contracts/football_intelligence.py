from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable


CONTRACT_VERSION = "apex-football-intelligence-v1"
MODEL_VERSION = "apex-fpl-native-football-primitives-v1"
ROLLOUT_MODE = "SHADOW_RESEARCH_ONLY"
PRODUCER_REPO = "mcnuggets651/fpl-apex"
COMPETITION_ID = "premier-league"

# These are the only report sources whose state is relevant to v1 primitives.
# Market, AIrsenal and optimisation source state is intentionally excluded.
PRIMITIVE_SOURCE_NAMES = {
    "official_fpl",
    "fpl_core_playerstats",
    "fpl_core_previous_season",
    "fpl_core_preseason",
    "tactical_inference",
    "manual_availability",
    "tactical_roles",
    "news_source_health",
    "news_feeds",
}

# Changing any of these columns must never affect football-intelligence payload values
# or selected-input hashes. They belong to FPL decision/ensemble or market surfaces.
FORBIDDEN_EXPORT_FIELDS = {
    "market_xp",
    "canonical_ev_xp",
    "risk_adjusted_xp",
    "weighted_xp",
    "official_xp",
    "airsenal_xp",
    "xp",
    "projection_confidence",
    "price",
    "selected_by_percent",
    "transfers_in",
    "transfers_out",
}

PLAYER_REPORT_FIELDS = (
    "player_id",
    "web_name",
    "team",
    "team_name",
    "position",
    "status",
    "chance_of_playing_next_round",
    "expected_minutes",
    "start_probability",
    "appearance_probability",
    "minutes_60_plus_probability",
    "minutes_confidence",
    "availability_probability",
    "tactical_role",
    "tactical_role_source",
    "role_confidence",
    "club_changed",
    "transfer_current_role_evidence",
    "penalty_share",
    "corners_share",
    "direct_freekick_share",
    "indirect_freekick_share",
    "availability_source_name",
    "availability_source_tier",
    "availability_source_url",
    "availability_evidence_type",
    "availability_published_at",
    "availability_retrieved_at",
    "availability_expires_at",
    "news_event_type",
    "news_source_name",
    "news_source_tier",
    "news_source_url",
    "news_published_at",
    "news_retrieved_at",
)

PROJECTION_PRIMITIVE_FIELDS = (
    "player_id",
    "gw",
    "opponent",
    "is_home",
    "attack_model_xg90",
    "attack_model_xa90",
    "xg_rate_credibility_adjusted",
    "xa_rate_credibility_adjusted",
    "attack_rate_reliability",
    "model_defensive_contribution_per_90",
    "defensive_rate_reliability",
)

POSITION_BY_ELEMENT_TYPE = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
SHA40 = re.compile(r"^[0-9a-f]{40}$")


class FootballIntelligenceContractError(ValueError):
    """Raised when an export input cannot satisfy the immutable v1 contract."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> Any:
    if not path.is_file():
        raise FootballIntelligenceContractError(f"required JSON file is missing: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FootballIntelligenceContractError(f"invalid JSON file {path}: {exc}") from exc


def _load_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FootballIntelligenceContractError(f"required CSV file is missing: {path}")
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise FootballIntelligenceContractError(f"CSV has no header: {path}")
            return [dict(row) for row in reader]
    except OSError as exc:
        raise FootballIntelligenceContractError(f"could not read CSV {path}: {exc}") from exc


def _require_columns(rows: list[dict[str, str]], required: Iterable[str], label: str) -> None:
    if not rows:
        raise FootballIntelligenceContractError(f"{label} is empty")
    missing = sorted(set(required) - set(rows[0]))
    if missing:
        raise FootballIntelligenceContractError(f"{label} missing required columns: {missing}")


def _parse_time(value: Any, label: str, *, allow_empty: bool = False) -> datetime | None:
    if value in (None, ""):
        if allow_empty:
            return None
        raise FootballIntelligenceContractError(f"{label} is required")
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise FootballIntelligenceContractError(f"{label} is not a valid ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise FootballIntelligenceContractError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value is not None else None


def _int(value: Any, label: str, *, allow_empty: bool = False) -> int | None:
    if value in (None, ""):
        if allow_empty:
            return None
        raise FootballIntelligenceContractError(f"{label} is required")
    try:
        number = float(str(value))
        integer = int(number)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FootballIntelligenceContractError(f"{label} must be an integer") from exc
    if number != integer:
        raise FootballIntelligenceContractError(f"{label} must be an integer")
    return integer


def _float(
    value: Any,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    allow_empty: bool = False,
) -> float | None:
    if value in (None, "", "nan", "NaN"):
        if allow_empty:
            return None
        raise FootballIntelligenceContractError(f"{label} is required")
    try:
        number = float(str(value))
    except (TypeError, ValueError, OverflowError) as exc:
        raise FootballIntelligenceContractError(f"{label} must be numeric") from exc
    if number != number or number in (float("inf"), float("-inf")):
        raise FootballIntelligenceContractError(f"{label} must be finite")
    if minimum is not None and number < minimum:
        raise FootballIntelligenceContractError(f"{label} must be >= {minimum}")
    if maximum is not None and number > maximum:
        raise FootballIntelligenceContractError(f"{label} must be <= {maximum}")
    return number


def _bool(value: Any, label: str, *, allow_empty: bool = False) -> bool | None:
    if value in (None, ""):
        if allow_empty:
            return None
        raise FootballIntelligenceContractError(f"{label} is required")
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise FootballIntelligenceContractError(f"{label} must be boolean")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _locator_hash(value: Any) -> str | None:
    text = _text(value)
    return _sha256_bytes(text.encode("utf-8")) if text else None


def _selected_rows_hash(rows: list[dict[str, str]], fields: tuple[str, ...]) -> str:
    selected: list[dict[str, str | None]] = []
    for row in rows:
        selected.append({field: (_text(row.get(field)) if field in row else None) for field in fields})
    return _sha256_json(selected)


def _constant_projection_value(
    rows: list[dict[str, str]],
    field: str,
    player_id: int,
    *,
    kind: str,
) -> float | bool:
    values: list[float | bool] = []
    for row in rows:
        if kind == "bool":
            parsed = _bool(row.get(field), f"projection player={player_id} {field}")
        else:
            parsed = _float(
                row.get(field),
                f"projection player={player_id} {field}",
                minimum=0.0,
            )
        assert parsed is not None
        values.append(parsed)
    if not values:
        raise FootballIntelligenceContractError(
            f"player {player_id} has no projection rows for {field}"
        )
    first = values[0]
    if any(value != first for value in values[1:]):
        raise FootballIntelligenceContractError(
            f"player {player_id} has fixture-varying {field}; v1 requires a player-level primitive"
        )
    return first


def _evidence_state(row: dict[str, str], prefix: str) -> dict[str, Any] | None:
    if prefix == "availability":
        source_name = _text(row.get("availability_source_name"))
        source_tier = _text(row.get("availability_source_tier"))
        source_url = row.get("availability_source_url")
        evidence_type = _text(row.get("availability_evidence_type"))
        published_raw = row.get("availability_published_at")
        retrieved_raw = row.get("availability_retrieved_at")
        expires_raw = row.get("availability_expires_at")
    else:
        source_name = _text(row.get("news_source_name"))
        source_tier = _text(row.get("news_source_tier"))
        source_url = row.get("news_source_url")
        evidence_type = _text(row.get("news_event_type"))
        published_raw = row.get("news_published_at")
        retrieved_raw = row.get("news_retrieved_at")
        expires_raw = None
    if not any((source_name, source_tier, _text(source_url), evidence_type, _text(published_raw))):
        return None
    published = _parse_time(published_raw, f"{prefix} published_at", allow_empty=True)
    retrieved = _parse_time(retrieved_raw, f"{prefix} retrieved_at", allow_empty=True)
    expires = _parse_time(expires_raw, f"{prefix} expires_at", allow_empty=True)
    return {
        "source_name": source_name,
        "source_tier": source_tier,
        "source_locator_sha256": _locator_hash(source_url),
        "evidence_type": evidence_type,
        "published_at": _iso(published),
        "retrieved_at": _iso(retrieved),
        "expires_at": _iso(expires),
    }


def _validate_evidence_times(state: dict[str, Any] | None, information_as_of: datetime, label: str) -> None:
    if state is None:
        return
    tolerance = timedelta(minutes=5)
    for field in ("published_at", "retrieved_at"):
        parsed = _parse_time(state.get(field), f"{label}.{field}", allow_empty=True)
        if parsed is not None and parsed > information_as_of + tolerance:
            raise FootballIntelligenceContractError(
                f"{label}.{field} is future-dated relative to information_as_of"
            )
    published = _parse_time(state.get("published_at"), f"{label}.published_at", allow_empty=True)
    retrieved = _parse_time(state.get("retrieved_at"), f"{label}.retrieved_at", allow_empty=True)
    if published is not None and retrieved is not None and retrieved < published:
        raise FootballIntelligenceContractError(f"{label} retrieval precedes publication")


def _build_official_identity(
    bootstrap: dict[str, Any],
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    elements = bootstrap.get("elements")
    teams = bootstrap.get("teams")
    if not isinstance(elements, list) or not isinstance(teams, list):
        raise FootballIntelligenceContractError(
            "official bootstrap snapshot must contain elements and teams lists"
        )
    team_map: dict[int, dict[str, Any]] = {}
    for raw in teams:
        team_id = _int(raw.get("id"), "official team.id")
        assert team_id is not None
        if team_id in team_map:
            raise FootballIntelligenceContractError(f"duplicate official team id {team_id}")
        name = _text(raw.get("name"))
        if not name:
            raise FootballIntelligenceContractError(f"official team {team_id} has no name")
        team_map[team_id] = {"id": team_id, "name": name}

    player_map: dict[int, dict[str, Any]] = {}
    for raw in elements:
        player_id = _int(raw.get("id"), "official player.id")
        team_id = _int(raw.get("team"), f"official player {player_id} team")
        element_type = _int(raw.get("element_type"), f"official player {player_id} element_type")
        assert player_id is not None and team_id is not None and element_type is not None
        if player_id in player_map:
            raise FootballIntelligenceContractError(f"duplicate official player id {player_id}")
        if team_id not in team_map:
            raise FootballIntelligenceContractError(
                f"official player {player_id} references unknown team {team_id}"
            )
        position = POSITION_BY_ELEMENT_TYPE.get(element_type)
        if position is None:
            raise FootballIntelligenceContractError(
                f"official player {player_id} has unsupported element_type {element_type}"
            )
        first = _text(raw.get("first_name")) or ""
        second = _text(raw.get("second_name")) or ""
        canonical_name = " ".join(part for part in (first, second) if part).strip()
        web_name = _text(raw.get("web_name"))
        if not canonical_name or not web_name:
            raise FootballIntelligenceContractError(
                f"official player {player_id} lacks canonical identity fields"
            )
        player_map[player_id] = {
            "id": player_id,
            "canonical_name": canonical_name,
            "web_name": web_name,
            "team_id": team_id,
            "position": position,
        }
    return player_map, team_map


def _build_fixtures(
    raw_fixtures: Any,
    team_map: dict[int, dict[str, Any]],
    gameweeks: list[int],
) -> tuple[list[dict[str, Any]], dict[tuple[int, int, int, bool], int]]:
    if not isinstance(raw_fixtures, list):
        raise FootballIntelligenceContractError("official fixtures snapshot must be a list")
    rows: list[dict[str, Any]] = []
    lookup: dict[tuple[int, int, int, bool], int] = {}
    seen_ids: set[int] = set()
    for raw in raw_fixtures:
        event = _int(raw.get("event"), "fixture.event", allow_empty=True)
        if event is None or event not in gameweeks:
            continue
        fixture_id = _int(raw.get("id"), "fixture.id")
        home = _int(raw.get("team_h"), f"fixture {fixture_id} team_h")
        away = _int(raw.get("team_a"), f"fixture {fixture_id} team_a")
        assert fixture_id is not None and home is not None and away is not None
        if fixture_id in seen_ids:
            raise FootballIntelligenceContractError(f"duplicate official fixture id {fixture_id}")
        seen_ids.add(fixture_id)
        if home == away or home not in team_map or away not in team_map:
            raise FootballIntelligenceContractError(f"fixture {fixture_id} has invalid team identity")
        kickoff = _parse_time(raw.get("kickoff_time"), f"fixture {fixture_id} kickoff_time")
        assert kickoff is not None
        rows.append(
            {
                "producer_fixture_id": f"fpl-fixture:{fixture_id}",
                "fpl_fixture_id": fixture_id,
                "gameweek": event,
                "scheduled_kickoff_utc": _iso(kickoff),
                "home_team": {
                    "producer_team_id": f"fpl-team:{home}",
                    "fpl_team_id": home,
                    "canonical_name": team_map[home]["name"],
                },
                "away_team": {
                    "producer_team_id": f"fpl-team:{away}",
                    "fpl_team_id": away,
                    "canonical_name": team_map[away]["name"],
                },
            }
        )
        for team, opponent, is_home in ((home, away, True), (away, home, False)):
            key = (event, team, opponent, is_home)
            if key in lookup:
                raise FootballIntelligenceContractError(f"ambiguous official fixture identity {key}")
            lookup[key] = fixture_id
    rows.sort(key=lambda row: (row["scheduled_kickoff_utc"], row["fpl_fixture_id"]))
    if not rows:
        raise FootballIntelligenceContractError("no official fixtures found for report gameweeks")
    return rows, lookup


def _source_health(report: dict[str, Any], information_as_of: datetime) -> list[dict[str, Any]]:
    raw_sources = report.get("sources")
    if not isinstance(raw_sources, list):
        raise FootballIntelligenceContractError("report sources must be a list")
    selected: list[dict[str, Any]] = []
    official_ok = False
    for raw in raw_sources:
        if not isinstance(raw, dict):
            raise FootballIntelligenceContractError("report source row must be an object")
        name = _text(raw.get("name"))
        if name not in PRIMITIVE_SOURCE_NAMES:
            continue
        checked = _parse_time(raw.get("checked_at"), f"source {name} checked_at", allow_empty=True)
        if checked is not None and checked > information_as_of + timedelta(minutes=5):
            raise FootballIntelligenceContractError(
                f"source {name} checked_at is future-dated relative to information_as_of"
            )
        ok = bool(raw.get("ok"))
        configured = bool(raw.get("configured", True))
        selected.append(
            {
                "name": name,
                "ok": ok,
                "configured": configured,
                "version": _text(raw.get("version")),
                "checked_at": _iso(checked),
            }
        )
        if name == "official_fpl":
            official_ok = ok and configured
    if not official_ok:
        raise FootballIntelligenceContractError(
            "official_fpl source must be healthy and configured to export identity"
        )
    selected.sort(key=lambda row: row["name"] or "")
    return selected


def build_football_intelligence_snapshot(
    report_dir: Path,
    snapshot_root: Path,
    *,
    producer_commit_sha: str,
    season: str,
    now: datetime | None = None,
    max_age_hours: float = 24.0,
) -> dict[str, Any]:
    """Build deterministic, market-independent football primitives from a finished FPL run.

    This function is deliberately downstream of the normal production pipeline. It
    reads existing report/snapshot artifacts and has no write path back into FPL state.
    """
    commit = producer_commit_sha.strip().lower()
    if not SHA40.fullmatch(commit):
        raise FootballIntelligenceContractError("producer_commit_sha must be a 40-char lowercase SHA")
    season_text = season.strip()
    if not season_text:
        raise FootballIntelligenceContractError("season is required")
    if max_age_hours <= 0:
        raise FootballIntelligenceContractError("max_age_hours must be positive")

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise FootballIntelligenceContractError("now must be timezone-aware")
    current = current.astimezone(timezone.utc)

    report_path = report_dir / "latest.json"
    players_path = report_dir / "players.csv"
    projections_path = report_dir / "projections.csv"
    report = _load_json(report_path)
    if not isinstance(report, dict):
        raise FootballIntelligenceContractError("report latest.json must be an object")
    information_as_of = _parse_time(report.get("generated_at"), "report.generated_at")
    assert information_as_of is not None
    if information_as_of > current + timedelta(minutes=5):
        raise FootballIntelligenceContractError("report.generated_at is future-dated")
    age_hours = (current - information_as_of).total_seconds() / 3600.0
    if age_hours > max_age_hours:
        raise FootballIntelligenceContractError(
            f"report is stale ({age_hours:.2f}h old; max {max_age_hours:.2f}h)"
        )

    raw_gameweeks = report.get("gameweeks")
    if not isinstance(raw_gameweeks, list) or not raw_gameweeks:
        raise FootballIntelligenceContractError("report gameweeks must be a non-empty list")
    gameweeks = [_int(value, "report gameweek") for value in raw_gameweeks]
    assert all(value is not None for value in gameweeks)
    gameweeks = [int(value) for value in gameweeks]
    if len(gameweeks) != len(set(gameweeks)) or gameweeks != sorted(gameweeks):
        raise FootballIntelligenceContractError("report gameweeks must be unique and sorted")

    official_meta = report.get("official_snapshot")
    if not isinstance(official_meta, dict):
        raise FootballIntelligenceContractError("report official_snapshot is required")
    snapshot_id = _text(official_meta.get("snapshot_id"))
    if not snapshot_id or Path(snapshot_id).name != snapshot_id:
        raise FootballIntelligenceContractError("official snapshot_id is invalid")
    snapshot_dir = snapshot_root / snapshot_id
    manifest_path = snapshot_dir / "manifest.json"
    bootstrap_path = snapshot_dir / "bootstrap-static.json"
    fixtures_path = snapshot_dir / "fixtures.json"
    manifest = _load_json(manifest_path)
    bootstrap = _load_json(bootstrap_path)
    raw_fixtures = _load_json(fixtures_path)
    if not isinstance(manifest, dict) or not isinstance(bootstrap, dict):
        raise FootballIntelligenceContractError("official snapshot files have invalid top-level type")

    for key in ("snapshot_id", "retrieved_at", "players", "fixtures", "bootstrap_sha256", "fixtures_sha256"):
        if str(manifest.get(key)) != str(official_meta.get(key)):
            raise FootballIntelligenceContractError(
                f"official snapshot manifest disagrees with report for {key}"
            )
    retrieved_at = _parse_time(manifest.get("retrieved_at"), "official snapshot retrieved_at")
    assert retrieved_at is not None
    if retrieved_at > information_as_of + timedelta(minutes=5):
        raise FootballIntelligenceContractError(
            "official snapshot retrieval is future-dated relative to report"
        )

    official_players, team_map = _build_official_identity(bootstrap)
    expected_players = _int(manifest.get("players"), "official manifest players")
    expected_fixtures = _int(manifest.get("fixtures"), "official manifest fixtures")
    assert expected_players is not None and expected_fixtures is not None
    if len(official_players) != expected_players:
        raise FootballIntelligenceContractError("official bootstrap player count disagrees with manifest")
    if not isinstance(raw_fixtures, list) or len(raw_fixtures) != expected_fixtures:
        raise FootballIntelligenceContractError("official fixtures count disagrees with manifest")

    fixtures, fixture_lookup = _build_fixtures(raw_fixtures, team_map, gameweeks)
    source_health = _source_health(report, information_as_of)

    player_rows = _load_csv(players_path)
    projection_rows = _load_csv(projections_path)
    _require_columns(player_rows, PLAYER_REPORT_FIELDS[:13], "players.csv")
    _require_columns(projection_rows, PROJECTION_PRIMITIVE_FIELDS, "projections.csv")

    report_player_map: dict[int, dict[str, str]] = {}
    for row in player_rows:
        player_id = _int(row.get("player_id"), "players.csv player_id")
        assert player_id is not None
        if player_id in report_player_map:
            raise FootballIntelligenceContractError(f"duplicate players.csv player_id {player_id}")
        report_player_map[player_id] = row
    if set(report_player_map) != set(official_players):
        missing = sorted(set(official_players) - set(report_player_map))[:20]
        extra = sorted(set(report_player_map) - set(official_players))[:20]
        raise FootballIntelligenceContractError(
            f"players.csv identity universe mismatch; missing={missing} extra={extra}"
        )

    projections_by_player: dict[int, list[dict[str, str]]] = {pid: [] for pid in official_players}
    seen_projection_fixtures: set[tuple[int, int, int, bool]] = set()
    projection_counts: dict[int, int] = {pid: 0 for pid in official_players}
    for row in projection_rows:
        player_id = _int(row.get("player_id"), "projections.csv player_id")
        gw = _int(row.get("gw"), f"projection player={player_id} gw")
        assert player_id is not None and gw is not None
        if player_id not in official_players:
            raise FootballIntelligenceContractError(
                f"projection references unknown official player {player_id}"
            )
        if gw not in gameweeks:
            continue
        projections_by_player[player_id].append(row)
        opponent = _int(
            row.get("opponent"),
            f"projection player={player_id} opponent",
            allow_empty=True,
        )
        is_home = _bool(
            row.get("is_home"),
            f"projection player={player_id} is_home",
            allow_empty=True,
        )
        if opponent is None and is_home is None:
            continue
        if opponent is None or is_home is None:
            raise FootballIntelligenceContractError(
                f"projection player={player_id} has incomplete fixture identity"
            )
        team_id = official_players[player_id]["team_id"]
        key = (gw, team_id, opponent, is_home)
        if key not in fixture_lookup:
            raise FootballIntelligenceContractError(
                f"projection player={player_id} does not match an official fixture: {key}"
            )
        unique_key = (player_id, gw, opponent, is_home)
        if unique_key in seen_projection_fixtures:
            raise FootballIntelligenceContractError(
                f"duplicate player/fixture projection identity {unique_key}"
            )
        seen_projection_fixtures.add(unique_key)
        projection_counts[player_id] += 1

    expected_team_fixture_counts: dict[int, int] = {team_id: 0 for team_id in team_map}
    for key in fixture_lookup:
        _gw, team_id, _opponent, _is_home = key
        expected_team_fixture_counts[team_id] += 1
    for player_id, official in official_players.items():
        if not projections_by_player[player_id]:
            raise FootballIntelligenceContractError(f"player {player_id} has no horizon projections")
        expected_count = expected_team_fixture_counts.get(official["team_id"], 0)
        if projection_counts[player_id] != expected_count:
            raise FootballIntelligenceContractError(
                f"player {player_id} fixture projection coverage mismatch: "
                f"{projection_counts[player_id]}/{expected_count}"
            )

    players_payload: list[dict[str, Any]] = []
    for player_id in sorted(official_players):
        official = official_players[player_id]
        row = report_player_map[player_id]
        report_team = _int(row.get("team"), f"player {player_id} team")
        if report_team != official["team_id"]:
            raise FootballIntelligenceContractError(f"player {player_id} club mismatch")
        report_position = _text(row.get("position"))
        if report_position != official["position"]:
            raise FootballIntelligenceContractError(f"player {player_id} position mismatch")
        if _text(row.get("web_name")) != official["web_name"]:
            raise FootballIntelligenceContractError(f"player {player_id} web_name mismatch")

        expected_minutes = _float(
            row.get("expected_minutes"), f"player {player_id} expected_minutes", minimum=0, maximum=90
        )
        start_probability = _float(
            row.get("start_probability"), f"player {player_id} start_probability", minimum=0, maximum=1
        )
        appearance_probability = _float(
            row.get("appearance_probability"),
            f"player {player_id} appearance_probability",
            minimum=0,
            maximum=1,
        )
        p60 = _float(
            row.get("minutes_60_plus_probability"),
            f"player {player_id} minutes_60_plus_probability",
            minimum=0,
            maximum=1,
        )
        minutes_confidence = _float(
            row.get("minutes_confidence"),
            f"player {player_id} minutes_confidence",
            minimum=0,
            maximum=1,
        )
        availability_probability = _float(
            row.get("availability_probability"),
            f"player {player_id} availability_probability",
            minimum=0,
            maximum=1,
        )
        assert None not in (
            expected_minutes,
            start_probability,
            appearance_probability,
            p60,
            minutes_confidence,
            availability_probability,
        )
        if start_probability > appearance_probability:
            raise FootballIntelligenceContractError(
                f"player {player_id} start_probability exceeds appearance_probability"
            )
        if p60 > appearance_probability:
            raise FootballIntelligenceContractError(
                f"player {player_id} 60+ probability exceeds appearance_probability"
            )

        projection_group = projections_by_player[player_id]
        xg90 = _constant_projection_value(
            projection_group, "attack_model_xg90", player_id, kind="float"
        )
        xa90 = _constant_projection_value(
            projection_group, "attack_model_xa90", player_id, kind="float"
        )
        xg_adjusted = _constant_projection_value(
            projection_group, "xg_rate_credibility_adjusted", player_id, kind="bool"
        )
        xa_adjusted = _constant_projection_value(
            projection_group, "xa_rate_credibility_adjusted", player_id, kind="bool"
        )
        attack_reliability = _constant_projection_value(
            projection_group, "attack_rate_reliability", player_id, kind="float"
        )
        defcon90 = _constant_projection_value(
            projection_group,
            "model_defensive_contribution_per_90",
            player_id,
            kind="float",
        )
        defensive_reliability = _constant_projection_value(
            projection_group, "defensive_rate_reliability", player_id, kind="float"
        )
        if not 0 <= float(attack_reliability) <= 1:
            raise FootballIntelligenceContractError(
                f"player {player_id} attack_rate_reliability outside [0,1]"
            )
        if not 0 <= float(defensive_reliability) <= 1:
            raise FootballIntelligenceContractError(
                f"player {player_id} defensive_rate_reliability outside [0,1]"
            )

        availability_evidence = _evidence_state(row, "availability")
        news_evidence = _evidence_state(row, "news")
        _validate_evidence_times(
            availability_evidence, information_as_of, f"player {player_id}.availability_evidence"
        )
        _validate_evidence_times(news_evidence, information_as_of, f"player {player_id}.news_evidence")

        set_piece: dict[str, float | None] = {}
        for output_name, source_name in (
            ("penalty_share", "penalty_share"),
            ("corner_share", "corners_share"),
            ("direct_free_kick_share", "direct_freekick_share"),
            ("indirect_free_kick_share", "indirect_freekick_share"),
        ):
            set_piece[output_name] = _float(
                row.get(source_name),
                f"player {player_id} {source_name}",
                minimum=0,
                maximum=1,
                allow_empty=True,
            )

        club_changed = _bool(row.get("club_changed"), f"player {player_id} club_changed", allow_empty=True)
        transfer_evidence = _float(
            row.get("transfer_current_role_evidence"),
            f"player {player_id} transfer_current_role_evidence",
            minimum=0,
            maximum=1,
            allow_empty=True,
        )
        role_confidence = _float(
            row.get("role_confidence"),
            f"player {player_id} role_confidence",
            minimum=0,
            maximum=1,
            allow_empty=True,
        )

        team_id = official["team_id"]
        players_payload.append(
            {
                "identity": {
                    "producer_player_id": f"fpl:{player_id}",
                    "fpl_player_id": player_id,
                    "canonical_name": official["canonical_name"],
                    "web_name": official["web_name"],
                    "team": {
                        "producer_team_id": f"fpl-team:{team_id}",
                        "fpl_team_id": team_id,
                        "canonical_name": team_map[team_id]["name"],
                    },
                    "position": official["position"],
                },
                "availability": {
                    "official_status": _text(row.get("status")),
                    "official_chance_percent": _float(
                        row.get("chance_of_playing_next_round"),
                        f"player {player_id} official chance",
                        minimum=0,
                        maximum=100,
                        allow_empty=True,
                    ),
                    "availability_probability": availability_probability,
                    "evidence": availability_evidence,
                },
                "minutes": {
                    "expected_minutes": expected_minutes,
                    "start_probability": start_probability,
                    "appearance_probability": appearance_probability,
                    "minutes_60_plus_probability": p60,
                    "confidence": minutes_confidence,
                },
                "tactical": {
                    "role": _text(row.get("tactical_role")) or "unknown",
                    "role_source": _text(row.get("tactical_role_source")) or "unknown",
                    "confidence": role_confidence,
                    "club_changed": club_changed,
                    "transfer_current_role_evidence": transfer_evidence,
                },
                "attacking_rates": {
                    "xg90": float(xg90),
                    "xa90": float(xa90),
                    "xg_rate_credibility_adjusted": bool(xg_adjusted),
                    "xa_rate_credibility_adjusted": bool(xa_adjusted),
                    "reliability": float(attack_reliability),
                },
                "defensive_rates": {
                    "defensive_contribution90": float(defcon90),
                    "reliability": float(defensive_reliability),
                },
                "set_pieces": set_piece,
                "news_state": news_evidence,
            }
        )

    selected_player_hash = _selected_rows_hash(player_rows, PLAYER_REPORT_FIELDS)
    selected_projection_hash = _selected_rows_hash(
        [row for row in projection_rows if _int(row.get("gw"), "projection gw") in gameweeks],
        PROJECTION_PRIMITIVE_FIELDS,
    )
    snapshot_hashes = {
        "official_bootstrap_source_sha256": _text(manifest.get("bootstrap_sha256")),
        "official_fixtures_source_sha256": _text(manifest.get("fixtures_sha256")),
        "persisted_bootstrap_sha256": _file_sha256(bootstrap_path),
        "persisted_fixtures_sha256": _file_sha256(fixtures_path),
        "official_manifest_sha256": _file_sha256(manifest_path),
        "player_primitive_subset_sha256": selected_player_hash,
        "projection_primitive_subset_sha256": selected_projection_hash,
    }
    input_lineage_id = "afi-input:" + _sha256_json(
        {
            "producer_commit_sha": commit,
            "season": season_text,
            "official_snapshot_id": snapshot_id,
            "source_snapshot_hashes": snapshot_hashes,
        }
    )

    safety = report.get("safety") if isinstance(report.get("safety"), dict) else {}
    payload = {
        "schema_version": CONTRACT_VERSION,
        "rollout_mode": ROLLOUT_MODE,
        "generated_at": _iso(information_as_of),
        "information_as_of": _iso(information_as_of),
        "producer": {
            "repository": PRODUCER_REPO,
            "commit_sha": commit,
            "model_version": MODEL_VERSION,
            "input_lineage_id": input_lineage_id,
        },
        "competition": {
            "competition_id": COMPETITION_ID,
            "name": "Premier League",
            "country": "England",
            "season": season_text,
        },
        "producer_readiness": {
            "safe_to_act": bool(report.get("safe_to_act")),
            "full_apex_ready": bool(report.get("full_apex_ready")),
            "blockers": sorted(str(item) for item in safety.get("blockers", []) if item),
            "warnings": sorted(str(item) for item in safety.get("warnings", []) if item),
        },
        "source_health": source_health,
        "source_snapshot_hashes": snapshot_hashes,
        "market_independence": {
            "policy": "pre_ensemble_apex_native_primitives_only",
            "verified_by_contract": True,
            "forbidden_source": "market_odds",
            "forbidden_export_fields": sorted(FORBIDDEN_EXPORT_FIELDS),
        },
        "source_governance": {
            "artifact_scope": "internal_private_research_only",
            "contains_raw_source_text": False,
            "contains_bookmaker_prices": False,
            "contains_betting_outcomes_or_edge": False,
            "code_license": "MIT",
            "upstream_data_rights_not_relicensed": True,
        },
        "capabilities": {
            "player_minutes": True,
            "player_start_appearance_probabilities": True,
            "player_xg_xa_rates": True,
            "player_defensive_contribution_rate": True,
            "tactical_role": True,
            "availability_news_state": True,
            "set_piece_shares_when_verified": True,
            "fixture_identity": True,
            "team_goal_surface": False,
            "shot_rate90": False,
            "shot_on_target_rate90": False,
            "betting_probability": False,
            "fpl_expected_points": False,
        },
        "official_snapshot": {
            "snapshot_id": snapshot_id,
            "retrieved_at": _iso(retrieved_at),
            "player_count": expected_players,
            "fixture_count": expected_fixtures,
        },
        "gameweeks": gameweeks,
        "fixtures": fixtures,
        "players": players_payload,
    }
    payload_sha = _sha256_json(payload)
    return {
        "artifact_id": f"afi-v1:{payload_sha[:24]}",
        "payload_sha256": payload_sha,
        "payload": payload,
    }


def write_football_intelligence_snapshot(snapshot: dict[str, Any], output: Path) -> None:
    """Write a canonical contract artifact exactly once."""
    expected = _text(snapshot.get("payload_sha256"))
    payload = snapshot.get("payload")
    if not expected or not isinstance(payload, dict):
        raise FootballIntelligenceContractError("snapshot envelope is malformed")
    actual = _sha256_json(payload)
    if actual != expected:
        raise FootballIntelligenceContractError("snapshot payload hash is invalid")
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded = _canonical_bytes(snapshot) + b"\n"
    try:
        with output.open("xb") as handle:
            handle.write(encoded)
    except FileExistsError as exc:
        raise FootballIntelligenceContractError(
            f"refusing to overwrite immutable football-intelligence artifact: {output}"
        ) from exc
