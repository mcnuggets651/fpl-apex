from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

from apex.sources.official import fetch_official_snapshot

PITCHSIDE_PUBLIC_DATA = (
    "https://bjarkisigur7.github.io/fpl-ai-assistant/data"
)


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _target_gameweek(official, now: datetime) -> int:
    future = [
        int(gameweek)
        for gameweek, value in official.deadlines.items()
        if _parse_utc(value) > now
    ]
    if not future:
        raise RuntimeError("no future Official FPL deadline for PITCHSIDE acquisition")
    return min(future)


def _get_json(http, url: str) -> tuple[bytes, object]:
    response = http.get(url, timeout=30)
    response.raise_for_status()
    raw = bytes(response.content)
    return raw, response.json()


def acquire_pitchside_shadow(
    output_path: str | Path,
    *,
    season: str,
    expected_official_hash: str | None,
    source_base_url: str = PITCHSIDE_PUBLIC_DATA,
    http=None,
    now: datetime | None = None,
) -> dict:
    """Acquire the public PITCHSIDE JSON bundle without granting serving authority.

    The source's ``next_gw`` metadata is intentionally not used as an alignment
    gate. Apex selects its own next actionable gameweek from Official FPL and
    requires that exact GW to exist in the source xP matrix. The source bundle
    must also predate the Official deadline for that GW, preventing hindsight.
    """

    http = http or requests.Session()
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    official, _ = fetch_official_snapshot(season=season)
    if expected_official_hash and official.source_hash != expected_official_hash:
        raise RuntimeError(
            "Official FPL authority changed before PITCHSIDE acquisition: "
            f"expected {expected_official_hash}, got {official.source_hash}"
        )

    target = _target_gameweek(official, now)
    deadline = _parse_utc(official.deadlines[target])
    base = source_base_url.rstrip("/")
    raw_meta, meta = _get_json(http, f"{base}/meta.json")
    raw_xp, xp = _get_json(http, f"{base}/xp.json")
    raw_players, players = _get_json(http, f"{base}/players.json")

    if not isinstance(meta, dict):
        raise RuntimeError("PITCHSIDE meta.json must be an object")
    if not isinstance(xp, dict):
        raise RuntimeError("PITCHSIDE xp.json must be an object")
    if not isinstance(players, list):
        raise RuntimeError("PITCHSIDE players.json must be an array")

    generated_at = str(meta.get("generated_utc") or "")
    if not generated_at:
        raise RuntimeError("PITCHSIDE generated_utc missing")
    if _parse_utc(generated_at) >= deadline:
        raise RuntimeError(
            "PITCHSIDE bundle was published at or after the target GW deadline"
        )

    source_season = int(meta.get("season", -1))
    official_start_year = int(str(season).split("-", 1)[0])
    if source_season != official_start_year:
        raise RuntimeError(
            f"PITCHSIDE season mismatch: {source_season} != {official_start_year}"
        )

    gws = [int(value) for value in xp.get("gws") or []]
    if target not in gws:
        raise RuntimeError(f"PITCHSIDE bundle has no forecast for target GW{target}")
    if not isinstance(xp.get("players"), dict):
        raise RuntimeError("PITCHSIDE xp.players must be an object")

    hashes = {
        "meta.json": hashlib.sha256(raw_meta).hexdigest(),
        "xp.json": hashlib.sha256(raw_xp).hexdigest(),
        "players.json": hashlib.sha256(raw_players).hexdigest(),
    }
    digest = hashlib.sha256()
    for name, raw in (
        ("meta.json", raw_meta),
        ("xp.json", raw_xp),
        ("players.json", raw_players),
    ):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(raw)
        digest.update(b"\0")

    official_after, _ = fetch_official_snapshot(season=season)
    if official_after.source_hash != official.source_hash:
        raise RuntimeError(
            "Official FPL authority changed during PITCHSIDE acquisition"
        )

    payload = {
        "schema_version": 1,
        "provider_id": "pitchside",
        "acquired_at": now.isoformat(),
        "expected_official_hash": official.source_hash,
        "target_gameweek": target,
        "target_deadline": official.deadlines[target],
        "source_base_url": base,
        "source_file_sha256": hashes,
        "bundle_sha256": digest.hexdigest(),
        "meta": meta,
        "xp": xp,
        "players": players,
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return {
        "provider_id": "pitchside",
        "target_gameweek": target,
        "generated_at": generated_at,
        "source_next_gw": meta.get("next_gw"),
        "available_gameweeks": gws,
        "player_vectors": len(xp["players"]),
        "bundle_sha256": payload["bundle_sha256"],
    }
