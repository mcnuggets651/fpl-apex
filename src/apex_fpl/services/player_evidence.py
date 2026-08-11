from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

import pandas as pd

from apex_fpl.data.news import TRUSTED_SOURCE_TIERS


CAPTAIN_MINUTES_CONFIDENCE_FLOOR = 0.75
HIGH_UNCERTAINTY_MINUTES_CONFIDENCE = 0.75
HIGH_UNCERTAINTY_ROLE_CONFIDENCE = 0.65
OFFICIAL_SOURCE_TIERS = {"official_club", "official_league"}


def _value(value: Any) -> Any:
    return None if pd.isna(value) else value


def _number(value: Any, default: float = 0.0) -> float:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return default if pd.isna(parsed) else float(parsed)


def _event_fingerprint(item: dict[str, Any]) -> str:
    text = " ".join(
        str(item.get(key) or "") for key in ("headline", "summary")
    ).casefold()
    normalised = " ".join(
        "".join(ch if ch.isalnum() else " " for ch in text).split()
    )
    return normalised or str(item.get("source_url") or "")


def _valid_current_source(
    *,
    tier: Any,
    url: Any,
    published_at: Any,
    expires_at: Any | None,
    now: pd.Timestamp,
) -> bool:
    if str(tier or "") not in TRUSTED_SOURCE_TIERS:
        return False
    if not str(url or "").startswith(("https://", "http://")):
        return False
    published = pd.to_datetime(published_at, utc=True, errors="coerce")
    if pd.isna(published) or published > now:
        return False
    if expires_at is not None and not pd.isna(expires_at):
        expires = pd.to_datetime(expires_at, utc=True, errors="coerce")
        if pd.isna(expires) or now > expires:
            return False
    return True


def build_selected_player_evidence(
    players: pd.DataFrame,
    news_audit: pd.DataFrame,
    selected_ids: Iterable[int],
    *,
    xi_ids: Iterable[int],
    captain_id: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build source-level dossiers and the exact publication coverage gate.

    A healthy HTTP feed is not evidence about a selected player. Coverage requires
    a current, attributable role/lineup, availability or set-piece item from a
    configured trusted tier. Statistical inference remains visible but cannot
    satisfy the deadline-evidence gate by itself.
    """
    now_value = pd.Timestamp(now or datetime.now(timezone.utc))
    now_utc = (
        now_value.tz_localize("UTC")
        if now_value.tzinfo is None
        else now_value.tz_convert("UTC")
    )
    selected = {int(pid) for pid in selected_ids}
    xi = {int(pid) for pid in xi_ids}
    indexed = players.drop_duplicates("player_id").set_index("player_id", drop=False)
    dossiers: list[dict[str, Any]] = []

    for player_id in sorted(selected):
        if player_id not in indexed.index:
            continue
        row = indexed.loc[player_id]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        evidence: list[dict[str, Any]] = []

        tactical_current = _valid_current_source(
            tier=row.get("source_tier"),
            url=row.get("source_url"),
            published_at=row.get("published_at"),
            expires_at=row.get("expires_at"),
            now=now_utc,
        )
        if any(
            pd.notna(row.get(col))
            for col in (
                "lineup_evidence_type",
                "source_name",
                "source_url",
                "published_at",
            )
        ):
            evidence.append(
                {
                    "evidence_type": _value(row.get("lineup_evidence_type")),
                    "source_name": _value(row.get("source_name")),
                    "source_tier": _value(row.get("source_tier")),
                    "source_url": _value(row.get("source_url")),
                    "published_at": _value(row.get("published_at")),
                    "retrieved_at": _value(row.get("retrieved_at")),
                    "expires_at": _value(row.get("expires_at")),
                    "eligible_for_decision": tactical_current,
                    "effect": "tactical_role_or_set_piece_override",
                }
            )

        availability_current = _valid_current_source(
            tier=row.get("availability_source_tier"),
            url=row.get("availability_source_url"),
            published_at=row.get("availability_published_at"),
            expires_at=row.get("availability_expires_at"),
            now=now_utc,
        )
        if any(
            pd.notna(row.get(col))
            for col in (
                "availability_evidence_type",
                "availability_source_name",
                "availability_source_url",
            )
        ):
            evidence.append(
                {
                    "evidence_type": _value(row.get("availability_evidence_type")),
                    "source_name": _value(row.get("availability_source_name")),
                    "source_tier": _value(row.get("availability_source_tier")),
                    "source_url": _value(row.get("availability_source_url")),
                    "published_at": _value(row.get("availability_published_at")),
                    "retrieved_at": _value(row.get("availability_retrieved_at")),
                    "expires_at": _value(row.get("availability_expires_at")),
                    "eligible_for_decision": availability_current,
                    "effect": "availability_multiplier",
                }
            )

        if not news_audit.empty and "player_id" in news_audit.columns:
            matches = news_audit[
                pd.to_numeric(news_audit["player_id"], errors="coerce").eq(player_id)
            ]
            for _, item in matches.iterrows():
                evidence.append(
                    {
                        "evidence_type": _value(item.get("evidence_type")),
                        "source_name": _value(item.get("source_name")),
                        "source_tier": _value(item.get("source_tier")),
                        "source_url": _value(item.get("source_url")),
                        "published_at": _value(item.get("published_at")),
                        "retrieved_at": _value(item.get("retrieved_at")),
                        "expires_at": None,
                        "eligible_for_decision": bool(
                            item.get("eligible_for_projection") is True
                            or item.get("eligible_for_projection") == 1
                        ),
                        "effect": {
                            "minutes_multiplier": _value(item.get("multiplier")),
                            "minutes_delta": _value(item.get("minutes_delta")),
                            "start_probability_delta": _value(
                                item.get("start_probability_delta")
                            ),
                        },
                        "headline": _value(item.get("headline")),
                        "summary": _value(item.get("summary")),
                        "ineligibility_reason": _value(
                            item.get("ineligibility_reason")
                        ),
                    }
                )

        current = [item for item in evidence if item["eligible_for_decision"]]
        current_sources = {
            str(item.get("source_name") or "").casefold() for item in current
        }
        official_current = any(
            str(item.get("source_tier") or "") in OFFICIAL_SOURCE_TIERS for item in current
        )
        trusted_current_sources = {
            str(item.get("source_name") or "").casefold()
            for item in current
            if str(item.get("source_tier") or "") == "trusted_media"
        }
        trusted_current_events = {
            _event_fingerprint(item)
            for item in current
            if str(item.get("source_tier") or "") == "trusted_media"
        }
        decision_grade = bool(
            official_current
            or (
                len(trusted_current_sources) >= 2
                and len(trusted_current_events) >= 2
            )
        )
        minutes_confidence = _number(row.get("minutes_confidence"))
        role_confidence = _number(row.get("role_confidence"))
        high_uncertainty = player_id in xi and (
            minutes_confidence < HIGH_UNCERTAINTY_MINUTES_CONFIDENCE
            or role_confidence < HIGH_UNCERTAINTY_ROLE_CONFIDENCE
        )
        dossiers.append(
            {
                "player_id": player_id,
                "web_name": _value(row.get("web_name")),
                "in_starting_xi": player_id in xi,
                "is_captain": player_id == int(captain_id),
                "expected_minutes": _value(row.get("expected_minutes")),
                "start_probability": _value(row.get("start_probability")),
                "minutes_confidence": minutes_confidence,
                "tactical_role": _value(row.get("tactical_role")),
                "role_source": _value(row.get("tactical_role_source")),
                "role_confidence": role_confidence,
                "high_uncertainty_starter": high_uncertainty,
                "evidence_state": _value(row.get("evidence_state")),
                "xi_evidence_eligible": bool(row.get("xi_evidence_eligible", True)),
                "captain_evidence_eligible": bool(
                    row.get("captain_evidence_eligible", True)
                ),
                "has_current_decision_evidence": bool(current),
                "has_decision_grade_evidence": decision_grade,
                "current_evidence_count": len(current),
                "independent_current_sources": len(current_sources),
                "official_current_evidence": official_current,
                "evidence": evidence,
            }
        )

    captain = next((row for row in dossiers if row["is_captain"]), None)
    high_uncertainty = [row for row in dossiers if row["high_uncertainty_starter"]]
    missing_high_uncertainty = [
        row["player_id"]
        for row in high_uncertainty
        if not row["has_decision_grade_evidence"]
    ]
    covered = [row for row in dossiers if row["has_current_decision_evidence"]]
    selected_xi_ineligible = [
        row["player_id"]
        for row in dossiers
        if row["in_starting_xi"] and not row["xi_evidence_eligible"]
    ]
    coverage = {
        "selected_players": len(dossiers),
        "selected_players_with_current_evidence": len(covered),
        "relevant_evidence_rows": sum(row["current_evidence_count"] for row in dossiers),
        "captain_id": int(captain_id),
        "captain_has_current_evidence": bool(
            captain and captain["has_current_decision_evidence"]
        ),
        "captain_has_decision_grade_evidence": bool(
            captain and captain["has_decision_grade_evidence"]
        ),
        "captain_minutes_confidence_floor": CAPTAIN_MINUTES_CONFIDENCE_FLOOR,
        "high_uncertainty_starter_ids": [row["player_id"] for row in high_uncertainty],
        "high_uncertainty_starters_missing_evidence": missing_high_uncertainty,
        "high_uncertainty_starters_missing_decision_grade_evidence": missing_high_uncertainty,
        "selected_xi_ineligible_ids": selected_xi_ineligible,
        "captain_evidence_eligible": bool(
            captain and captain["captain_evidence_eligible"]
        ),
        "ready": bool(
            captain
            and captain["captain_evidence_eligible"]
            and not selected_xi_ineligible
        ),
    }
    return {"contract": "apex-player-evidence-v2", "coverage": coverage, "dossiers": dossiers}
