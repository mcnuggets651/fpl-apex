from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
import os
import re
import statistics
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

EXPECTED_PROVIDERS = (
    "airsenal",
    "apex_proprietary",
    "dastan",
    "pitchside",
    "openfpl",
)
INTERNAL_PROVIDERS = ("airsenal", "apex_proprietary", "dastan")
EXTERNAL_PROVIDERS = ("pitchside", "openfpl")
PROJECTION_PROVIDER_SET = frozenset(EXPECTED_PROVIDERS)
INTERNAL_PROVIDER_SET = frozenset(INTERNAL_PROVIDERS)
CHAMPION_PROVIDER = "airsenal"
UNIVERSAL_HORIZON = 1
STRATEGIC_HORIZONS = tuple(range(2, 9))
ALL_HORIZONS = tuple(range(1, 9))
DEFAULT_MAX_AGE_HOURS = 18.0
PITCHSIDE_BASE = "https://bjarkisigur7.github.io/fpl-ai-assistant/data"
FPL_BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_FIXTURES = "https://fantasy.premierleague.com/api/fixtures/"
FPL_LIVE = "https://fantasy.premierleague.com/api/event/{gameweek}/live/"

DNS_TRAINING_NOT_READY = "TRAINING_NOT_READY"
DNS_TRAINING_READY_NO_MODEL = "TRAINING_READY_NO_MODEL"
DNS_EXPORT_MISSING = "PROVIDER_EXPORT_MISSING"
DNS_INCOMPLETE_UNIVERSE = "INCOMPLETE_UNIVERSE"
DNS_FORECAST_STALE = "FORECAST_STALE"
DNS_SCHEMA_INVALID = "SCHEMA_INVALID"
DNS_OFFICIAL_HASH = "OFFICIAL_HASH_MISMATCH"
DNS_TARGET = "TARGET_MISMATCH"
DNS_AFTER_CUTOFF = "SUBMISSION_AFTER_CUTOFF"
DNS_NO_H1 = "NO_H1_FORECAST"
DNS_ARTIFACT = "ARTIFACT_HASH_MISSING"
DNS_UNQUALIFIED = "UNQUALIFIED"
DNS_UPSTREAM = "UPSTREAM_UNAVAILABLE"

GW2_CLASSIFICATION = "DIAGNOSTIC_REHEARSAL_NON_CANONICAL"
PROSPECTIVE_READY_CANDIDATE = "PROSPECTIVE_READY_CANDIDATE"
PROSPECTIVE_NOT_READY = "PROSPECTIVE_NOT_READY"
CANONICAL_PROSPECTIVE_OBSERVATION = "CANONICAL_PROSPECTIVE_OBSERVATION"

CANDIDATE_PREFIX = "apex-v2/tournament-candidate"
PRIVATE_TOURNAMENT_PREFIX = "apex-v2/private-tournament"
SELECTION_PREFIX = "apex-v2/tournament-selection"
EVALUATION_PREFIX = "apex-v2/tournament-evaluation"
GW2_DIAGNOSTIC_PREFIX = "apex-v2/tournament-diagnostic"


class TournamentContractError(RuntimeError):
    pass


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(canonical_bytes(payload) + b"\n")
    os.replace(tmp, path)
    return path


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TournamentContractError(f"JSON object required: {path}")
    return payload


def _release_asset_map(release: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(asset["name"]): asset for asset in release.get("assets", [])}


def _find_release(releases: Iterable[dict[str, Any]], tag: str) -> dict[str, Any] | None:
    return next(
        (
            row
            for row in releases
            if str(row.get("tag_name") or "") == str(tag) and not row.get("draft")
        ),
        None,
    )


def _write_deterministic_tar_gz(output: Path, members: dict[str, bytes]) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w", format=tarfile.USTAR_FORMAT) as archive:
                for name, data in sorted(members.items()):
                    info = tarfile.TarInfo(name=name)
                    info.size = len(data)
                    info.mtime = 0
                    info.mode = 0o644
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    archive.addfile(info, io.BytesIO(data))
    return output


def _http_json(session: Any, url: str, *, timeout: float = 30.0) -> tuple[bytes, Any]:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    raw = bytes(response.content)
    return raw, response.json()


def _next_actionable_event(bootstrap: dict[str, Any], now: datetime) -> dict[str, Any]:
    future = []
    for event in bootstrap.get("events") or []:
        deadline = event.get("deadline_time")
        if event.get("id") is None or not deadline:
            continue
        try:
            when = _parse_utc(str(deadline))
        except Exception:
            continue
        if when > now:
            future.append((when, event))
    if not future:
        raise TournamentContractError("Official FPL exposes no future deadline")
    return min(future, key=lambda pair: pair[0])[1]


def _fixture_ids(
    fixtures: list[dict[str, Any]],
    *,
    team_id: int,
    gameweek: int,
) -> list[int]:
    output = []
    for fixture in fixtures:
        event = fixture.get("event")
        if event is None or int(event) != int(gameweek):
            continue
        if int(team_id) not in {int(fixture.get("team_h", -1)), int(fixture.get("team_a", -1))}:
            continue
        if fixture.get("id") is not None:
            output.append(int(fixture["id"]))
    return sorted(output)


def _run_current_official_hash(*, season: str) -> str:
    result = subprocess.run(
        ["apex-v2", "official-hash", "--season", str(season)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    value = result.stdout.strip().splitlines()[-1].strip() if result.stdout.strip() else ""
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower()):
        raise TournamentContractError("apex-v2 official-hash did not return a SHA-256 digest")
    return value.lower()


def capture_pitchside(
    *,
    season: str,
    target_gameweek: int,
    expected_official_hash: str,
    deadline: datetime,
    output: Path,
    current_official_hash: str | None = None,
    now: datetime | None = None,
    session: Any = None,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
) -> dict[str, Any]:
    """Capture a no-hindsight PITCHSIDE tournament surface outside serving certification.

    The exact Apex Official hash is re-checked before the capture is eligible. Players
    with Official status ``u`` are retained as explicit NO_FORECAST rows; they do not
    count as missing forecastable players. Every other Official player must have a
    finite forecast for a horizon to qualify that horizon.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    expected_official_hash = str(expected_official_hash).lower()
    if len(expected_official_hash) != 64:
        raise TournamentContractError("expected Official hash must be SHA-256")
    current = (current_official_hash or _run_current_official_hash(season=season)).lower()
    result: dict[str, Any] = {
        "schema_version": 1,
        "provider_id": "pitchside",
        "production_influence": "NONE",
        "serve_authorized": False,
        "season": str(season),
        "target_gameweek": int(target_gameweek),
        "expected_official_hash": expected_official_hash,
        "current_official_hash": current,
        "checked_at": now.isoformat(),
    }
    if current != expected_official_hash:
        result.update(
            {
                "health": "ERROR",
                "dns_code": DNS_OFFICIAL_HASH,
                "reasons": ["current exact Official hash no longer matches source production seal"],
                "surface": None,
            }
        )
        _write_json(output, result)
        return result

    http = session or requests.Session()
    try:
        raw_bootstrap, bootstrap = _http_json(http, FPL_BOOTSTRAP)
        raw_fixtures, fixtures = _http_json(http, FPL_FIXTURES)
        raw_meta, meta = _http_json(http, f"{PITCHSIDE_BASE}/meta.json")
        raw_xp, xp = _http_json(http, f"{PITCHSIDE_BASE}/xp.json")
        raw_players, source_players = _http_json(http, f"{PITCHSIDE_BASE}/players.json")
        raw_meta_after, meta_after = _http_json(http, f"{PITCHSIDE_BASE}/meta.json")
        if raw_meta_after != raw_meta or meta_after != meta:
            raise TournamentContractError("PITCHSIDE deployment changed during acquisition")
        if not isinstance(bootstrap, dict) or not isinstance(fixtures, list):
            raise TournamentContractError("Official public payload schema invalid")
        if not isinstance(meta, dict) or not isinstance(xp, dict) or not isinstance(source_players, list):
            raise TournamentContractError("PITCHSIDE public bundle schema invalid")

        event = _next_actionable_event(bootstrap, now)
        live_target = int(event["id"])
        live_deadline = _parse_utc(str(event["deadline_time"]))
        if live_target != int(target_gameweek):
            raise TournamentContractError(
                f"Official target changed during external capture: {live_target} != {target_gameweek}"
            )
        if live_deadline != deadline.astimezone(timezone.utc):
            raise TournamentContractError("Official deadline changed relative to source production seal")

        generated_raw = str(meta.get("generated_utc") or "")
        if not generated_raw:
            raise TournamentContractError("PITCHSIDE generated_utc missing")
        generated = _parse_utc(generated_raw)
        age_hours = (now - generated).total_seconds() / 3600.0
        if generated >= deadline:
            raise TournamentContractError("PITCHSIDE forecast was generated at/after target deadline")
        if age_hours < -0.1:
            raise TournamentContractError("PITCHSIDE generated timestamp is in the future")

        source_season = int(meta.get("season", -1))
        expected_start = int(str(season).split("-", 1)[0])
        if source_season != expected_start:
            raise TournamentContractError(
                f"PITCHSIDE season mismatch: {source_season} != {expected_start}"
            )
        gws = [int(value) for value in xp.get("gws") or []]
        forecasts = xp.get("players")
        if not isinstance(forecasts, dict):
            raise TournamentContractError("PITCHSIDE xp.players must be an object")
        selected_gws = [
            gw
            for gw in gws
            if int(target_gameweek) <= gw < int(target_gameweek) + len(ALL_HORIZONS)
        ]
        if int(target_gameweek) not in selected_gws:
            raise TournamentContractError(f"PITCHSIDE has no target GW{target_gameweek} forecast")
        gw_index = {gw: gws.index(gw) for gw in selected_gws}

        elements = bootstrap.get("elements") or []
        code_to_element: dict[int, dict[str, Any]] = {}
        for player in elements:
            if player.get("code") is None or player.get("id") is None:
                continue
            code = int(player["code"])
            if code in code_to_element:
                raise TournamentContractError(f"duplicate Official player code {code}")
            code_to_element[code] = player

        rows: list[dict[str, Any]] = []
        missing_forecastable: dict[str, list[int]] = {str(h): [] for h in ALL_HORIZONS}
        forecast_counts: dict[str, int] = {str(h): 0 for h in ALL_HORIZONS}
        unavailable_counts: dict[str, int] = {str(h): 0 for h in ALL_HORIZONS}
        forecastable_ids = {
            int(player["id"])
            for player in elements
            if player.get("id") is not None and str(player.get("status") or "") != "u"
        }
        unavailable_ids = {
            int(player["id"])
            for player in elements
            if player.get("id") is not None and str(player.get("status") or "") == "u"
        }

        by_code: dict[int, list[Any]] = {}
        for raw_code, values in forecasts.items():
            try:
                code = int(raw_code)
            except (TypeError, ValueError):
                continue
            if not isinstance(values, list) or len(values) != len(gws):
                raise TournamentContractError(f"PITCHSIDE xP vector length mismatch for code {raw_code}")
            by_code[code] = values

        for code, player in sorted(code_to_element.items(), key=lambda pair: int(pair[1]["id"])):
            element_id = int(player["id"])
            status = str(player.get("status") or "")
            values = by_code.get(code)
            for gw in selected_gws:
                horizon = gw - int(target_gameweek) + 1
                raw_value = values[gw_index[gw]] if values is not None else None
                reason = None
                coverage_status = "FORECAST"
                expected_points: float | None = None
                if raw_value is not None:
                    expected_points = float(raw_value)
                    if not math.isfinite(expected_points):
                        raise TournamentContractError(
                            f"PITCHSIDE non-finite xP for element {element_id}, GW{gw}"
                        )
                    forecast_counts[str(horizon)] += 1
                elif status == "u":
                    coverage_status = "NO_FORECAST"
                    reason = "OFFICIAL_UNAVAILABLE_NO_FORECAST_EXPECTED"
                    unavailable_counts[str(horizon)] += 1
                else:
                    coverage_status = "NO_FORECAST"
                    reason = "PITCHSIDE_MISSING_FORECASTABLE_PLAYER"
                    missing_forecastable[str(horizon)].append(element_id)
                fixture_ids = _fixture_ids(
                    fixtures,
                    team_id=int(player.get("team") or 0),
                    gameweek=gw,
                )
                rows.append(
                    {
                        "element_id": element_id,
                        "gameweek": gw,
                        "horizon": horizon,
                        "expected_points": expected_points,
                        "fixture_ids": fixture_ids,
                        "n_fixtures": len(fixture_ids),
                        "player_status_at_forecast": status,
                        "expected_minutes": None,
                        "p_appearance": None,
                        "p_start": None,
                        "p_60": None,
                        "coverage_status": coverage_status,
                        "coverage_reason": reason,
                        "metadata": {"pitchside_player_code": code},
                    }
                )

        qualified_horizons = [
            h
            for h in ALL_HORIZONS
            if h <= len(selected_gws) and not missing_forecastable[str(h)]
        ]
        source_hashes = {
            "meta.json": _sha256_bytes(raw_meta),
            "xp.json": _sha256_bytes(raw_xp),
            "players.json": _sha256_bytes(raw_players),
            "official_bootstrap.json": _sha256_bytes(raw_bootstrap),
            "official_fixtures.json": _sha256_bytes(raw_fixtures),
        }
        bundle_sha = canonical_sha256(source_hashes)
        health = "HEALTHY"
        reasons: list[str] = []
        if age_hours > float(max_age_hours):
            health = "STALE"
            reasons.append(
                f"source age {age_hours:.2f}h exceeds governed {float(max_age_hours):.2f}h"
            )
        missing_h1 = missing_forecastable["1"]
        if missing_h1:
            health = "INCOMPLETE" if health == "HEALTHY" else health
            reasons.append(
                f"H1 missing {len(missing_h1)} forecastable Official players: {missing_h1}"
            )
        for h in ALL_HORIZONS[1:]:
            if h <= len(selected_gws) and missing_forecastable[str(h)]:
                reasons.append(
                    f"H{h} missing {len(missing_forecastable[str(h)])} forecastable Official players"
                )
        surface = {
            "schema_version": 1,
            "provider_id": "pitchside",
            "provider_version": str(meta.get("model_version") or bundle_sha),
            "generated_at": generated.isoformat(),
            "season": str(season),
            "source_snapshot": f"pitchside:{bundle_sha}",
            "scoring_rules_version": f"fpl-{season}-current",
            "supported_horizons": list(range(1, len(selected_gws) + 1)),
            "runtime_dependencies": [PITCHSIDE_BASE],
            "rows": sorted(rows, key=lambda row: (int(row["horizon"]), int(row["element_id"]))),
        }
        result.update(
            {
                "health": health,
                "dns_code": (
                    None
                    if health == "HEALTHY"
                    else DNS_FORECAST_STALE
                    if health == "STALE"
                    else DNS_INCOMPLETE_UNIVERSE
                ),
                "reasons": reasons,
                "generated_at": generated.isoformat(),
                "age_hours": round(age_hours, 4),
                "deadline": deadline.astimezone(timezone.utc).isoformat(),
                "official_player_count": len(elements),
                "forecastable_player_count": len(forecastable_ids),
                "official_unavailable_player_count": len(unavailable_ids),
                "qualified_horizons": qualified_horizons,
                "forecast_counts_by_horizon": forecast_counts,
                "unavailable_no_forecast_expected_by_horizon": unavailable_counts,
                "missing_forecastable_ids_by_horizon": missing_forecastable,
                "source_file_sha256": source_hashes,
                "source_bundle_sha256": bundle_sha,
                "surface_sha256": canonical_sha256(surface),
                "surface": surface,
            }
        )
    except Exception as exc:
        result.update(
            {
                "health": "ERROR",
                "dns_code": DNS_UPSTREAM,
                "reasons": [f"{type(exc).__name__}: {exc}"],
                "surface": None,
            }
        )
    _write_json(output, result)
    return result


def verify_public_release_files(files: dict[str, Path]) -> dict[str, Any]:
    required = {
        "public_attempt.json",
        "provider_forecasts.tar.gz",
        "governance.json",
        "attestation.json",
    }
    if not required.issubset(files):
        raise TournamentContractError(
            f"source final missing tournament-required public assets: {sorted(required - set(files))}"
        )
    public_attempt = _load_json(files["public_attempt.json"])
    governance = _load_json(files["governance.json"])
    attestation = _load_json(files["attestation.json"])
    if str(attestation.get("scope") or "") != "PUBLIC":
        raise TournamentContractError("public attestation scope mismatch")
    if str(attestation.get("public_attempt_id") or "") != str(public_attempt.get("public_attempt_id") or ""):
        raise TournamentContractError("public attempt identity mismatch")
    assets = attestation.get("assets") or {}
    for name in required - {"attestation.json"}:
        expected = str(assets.get(name) or "")
        actual = sha256_path(files[name])
        if expected != actual:
            raise TournamentContractError(f"source final attestation mismatch: {name}")
    if str(governance.get("season") or "") != str(public_attempt.get("season") or ""):
        raise TournamentContractError("governance/public season mismatch")
    if int(governance.get("target_gameweek", -1)) != int(public_attempt.get("target_gameweek", -2)):
        raise TournamentContractError("governance/public target mismatch")
    return public_attempt


def _internal_qualification(governance: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = governance.get("qualification_matrix") or []
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        pid = str(row.get("provider_id") or "")
        if not pid:
            continue
        if pid in output:
            raise TournamentContractError(f"duplicate qualification row: {pid}")
        output[pid] = row
    missing = sorted(INTERNAL_PROVIDER_SET - set(output))
    if missing:
        raise TournamentContractError(
            "production governance silently omitted internal tournament provider(s): "
            + ", ".join(missing)
        )
    return {pid: output[pid] for pid in INTERNAL_PROVIDERS}


def _qualified_horizons(row: dict[str, Any]) -> tuple[int, ...]:
    matrix = row.get("qualification_by_horizon") or {}
    out = []
    for horizon, status in matrix.items():
        try:
            h = int(horizon)
        except (TypeError, ValueError):
            continue
        if str(status).upper() == "QUALIFIED":
            out.append(h)
    return tuple(sorted(set(out)))


def _surface_rows(surface: dict[str, Any], horizon: int) -> list[dict[str, Any]]:
    rows = []
    for row in surface.get("rows") or []:
        if not isinstance(row, dict):
            continue
        try:
            if int(row.get("horizon", -1)) == int(horizon):
                rows.append(row)
        except (TypeError, ValueError):
            continue
    return rows


def _forecast_ids(surface: dict[str, Any], horizon: int) -> frozenset[int]:
    output: set[int] = set()
    for row in _surface_rows(surface, horizon):
        if str(row.get("coverage_status") or "FORECAST").upper() != "FORECAST":
            continue
        if row.get("expected_points") is None:
            continue
        try:
            value = float(row["expected_points"])
            pid = int(row["element_id"])
        except (TypeError, ValueError, KeyError):
            continue
        if math.isfinite(value):
            output.add(pid)
    return frozenset(output)


def _no_forecast_ids(surface: dict[str, Any], horizon: int) -> frozenset[int]:
    output: set[int] = set()
    for row in _surface_rows(surface, horizon):
        if str(row.get("coverage_status") or "").upper() != "FORECAST":
            try:
                output.add(int(row["element_id"]))
            except (TypeError, ValueError, KeyError):
                pass
    return frozenset(output)


def _openfpl_dns(readiness: dict[str, Any] | None) -> tuple[str, list[str], str]:
    if not readiness:
        return DNS_EXPORT_MISSING, ["OpenFPL readiness artifact missing"], "UNKNOWN"
    state = str(readiness.get("state") or "UNKNOWN")
    reasons = [str(value) for value in readiness.get("reasons") or []]
    if state in {"DEFERRED_BY_GOVERNANCE", "CURRENT_LABEL_HISTORY_INSUFFICIENT"}:
        return DNS_TRAINING_NOT_READY, [state, *reasons], state
    if state in {"READY_FOR_SHADOW_BUILD", "TRAINING_READY_NO_MODEL"}:
        return DNS_TRAINING_READY_NO_MODEL, [state, *reasons], state
    if readiness.get("model_export_available") is True:
        return DNS_EXPORT_MISSING, ["model marked available but no tournament surface was supplied"], state
    return DNS_EXPORT_MISSING, [state, *reasons], state


def _scoreable_tasks(surface: dict[str, Any] | None, *, entered: bool, horizon: int = 1) -> dict[str, bool]:
    rows = _surface_rows(surface or {}, horizon)
    return {
        "player_xp": bool(entered),
        "player_ranking": bool(entered),
        "captain_ranking": bool(entered and horizon == 1),
        "minutes": bool(entered and any(row.get("expected_minutes") is not None for row in rows)),
        "appearance_probability": bool(entered and any(row.get("p_appearance") is not None for row in rows)),
        "start_probability": bool(entered and any(row.get("p_start") is not None for row in rows)),
        "p60_probability": bool(entered and any(row.get("p_60") is not None for row in rows)),
        "attacking_return": bool(
            entered
            and any(
                any(key in row for key in ("p_goal", "p_assist", "p_attacking_return"))
                for row in rows
            )
        ),
        "clean_sheet_defensive": bool(
            entered
            and any(
                any(key in row for key in ("p_clean_sheet", "p_cs", "expected_clean_sheet_points"))
                for row in rows
            )
        ),
        "bonus": bool(entered and any(any(key in row for key in ("expected_bonus", "p_bonus")) for row in rows)),
    }
