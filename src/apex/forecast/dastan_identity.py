from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class ClubOverlayRow:
    club_name: str
    understat_name: str
    understat_team_id: int


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def payload_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def resolve_understat_clubs(
    team_payload: Mapping[str, Any],
    *,
    aliases: Mapping[str, Iterable[str]],
) -> tuple[ClubOverlayRow, ...]:
    """Resolve an explicitly permitted FPL club list against one live Understat league payload.

    This deliberately has no fuzzy matching. A club is accepted only when exactly one
    Understat team title matches one of the reviewed aliases after punctuation/spacing
    normalization. Zero or multiple candidates are a hard error.
    """
    available: list[tuple[int, str]] = []
    for raw_id, raw in team_payload.items():
        if not isinstance(raw, Mapping):
            continue
        title = raw.get("title") or raw.get("name") or raw.get("team_name")
        if not title:
            continue
        try:
            team_id = int(raw_id)
        except (TypeError, ValueError):
            explicit = raw.get("id")
            if explicit is None:
                continue
            team_id = int(explicit)
        available.append((team_id, str(title)))

    resolved: list[ClubOverlayRow] = []
    for club_name, reviewed_aliases in aliases.items():
        accepted = {_norm(club_name), *(_norm(value) for value in reviewed_aliases)}
        matches = [item for item in available if _norm(item[1]) in accepted]
        if len(matches) != 1:
            raise RuntimeError(
                f"Understat club resolution for {club_name!r} expected exactly one "
                f"reviewed-alias match, got {matches}"
            )
        team_id, title = matches[0]
        resolved.append(ClubOverlayRow(club_name, title, team_id))
    return tuple(resolved)


def audit_current_roster(
    official_elements: Iterable[Mapping[str, Any]],
    dastan_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare current Official FPL identities to Dastan by stable FPL code.

    Element-ID drift is reported, never treated as an identity mismatch. Name matching is
    intentionally absent: a player exists in the shared identity universe only when the
    stable Official FPL ``code`` agrees.
    """
    official: dict[int, Mapping[str, Any]] = {}
    for row in official_elements:
        code = row.get("code")
        if code is None:
            raise ValueError("Official FPL element missing stable code")
        code = int(code)
        if code in official:
            raise ValueError(f"Official FPL duplicate stable code {code}")
        official[code] = row

    dastan: dict[int, Mapping[str, Any]] = {}
    for row in dastan_rows:
        code = int(row["fpl_code"])
        if code in dastan:
            raise ValueError(f"Dastan duplicate stable FPL code {code}")
        dastan[code] = row

    common = sorted(set(official) & set(dastan))
    missing = sorted(set(official) - set(dastan))
    stale = sorted(set(dastan) - set(official))
    element_drift = []
    unresolved_understat = []
    for code in common:
        off = official[code]
        ds = dastan[code]
        if ds.get("element") not in (None, "") and int(ds["element"]) != int(off["id"]):
            element_drift.append(
                {
                    "fpl_code": code,
                    "dastan_element": int(ds["element"]),
                    "official_element": int(off["id"]),
                }
            )
        understat = ds.get("understat_id")
        if understat in (None, "") or str(ds.get("mapping_status", "")).casefold() != "mapped":
            unresolved_understat.append(code)

    return {
        "official_players": len(official),
        "dastan_roster_players": len(dastan),
        "matched_by_fpl_code": len(common),
        "missing_from_dastan_roster": missing,
        "stale_dastan_codes": stale,
        "element_id_drift": element_drift,
        "unresolved_understat_codes": sorted(unresolved_understat),
        "identity_match_rate": (len(common) / len(official)) if official else 0.0,
    }
