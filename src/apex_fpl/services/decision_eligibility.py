from __future__ import annotations

import json
import pandas as pd

from apex_fpl.data.news import TRUSTED_SOURCE_TIERS


# Quantitative uncertainty is not a hard captain floor. Expected minutes/availability
# already reduce production xP and exact captain/vice mechanics price no-show fallback.
# Only attributable adverse evidence can exclude pre-solve.
MIN_CAPTAIN_EXPECTED_MINUTES = 0.0
MIN_CAPTAIN_START_PROBABILITY = 0.0
MIN_CAPTAIN_APPEARANCE_PROBABILITY = 0.0
MIN_CAPTAIN_PROJECTION_CONFIDENCE = 0.0
MIN_SOURCE_HEALTH_RATIO = 2 / 3
MIN_HEALTHY_NEWS_SOURCES = 2
MIN_FRESH_NEWS_ITEMS = 1
SOURCE_HEALTH_WINDOW_HOURS = 120.0


def source_health_status(sources: list) -> dict:
    """Measure news-source health without turning it into a global production kill switch.

    Current news is important when a selected player's minutes/role state is uncertain.
    That materiality is enforced by ``build_selected_player_evidence``. A feed outage
    about unrelated players must not invalidate an otherwise fully supported decision.
    ``ready`` therefore means the diagnostic was evaluated; ``healthy_contract_met``
    records whether the preferred redundant-news surface is currently healthy.
    """
    row = next((s for s in sources if getattr(s, "name", "") == "news_source_health"), None)
    try:
        measured = json.loads(getattr(row, "version", "") or "{}")
    except json.JSONDecodeError:
        measured = {}
    configured = int(measured.get("configured_sources", 0) or 0)
    healthy = int(measured.get("healthy_sources", 0) or 0)
    fresh = int(measured.get("fresh_timestamped_items", 0) or 0)
    ratio = healthy / configured if configured else 0.0
    healthy_contract_met = bool(
        configured >= 2
        and healthy >= MIN_HEALTHY_NEWS_SOURCES
        and ratio >= MIN_SOURCE_HEALTH_RATIO
        and fresh >= MIN_FRESH_NEWS_ITEMS
    )
    return {
        "contract": "apex-news-source-health-v2",
        "ready": True,
        "healthy_contract_met": healthy_contract_met,
        "degraded": not healthy_contract_met,
        "configured_sources": configured,
        "healthy_sources": healthy,
        "healthy_ratio": ratio,
        "fresh_timestamped_items": fresh,
        "window_hours": SOURCE_HEALTH_WINDOW_HOURS,
        "minimum_healthy_sources": MIN_HEALTHY_NEWS_SOURCES,
        "minimum_healthy_ratio": MIN_SOURCE_HEALTH_RATIO,
        "minimum_fresh_timestamped_items": MIN_FRESH_NEWS_ITEMS,
        "policy": "diagnostic_global_health_selected_player_materiality_gate",
    }


def _normalise_event(row: pd.Series) -> str:
    """Fingerprint an underlying story so syndicated copies count once."""
    text = " ".join(str(row.get(k) or "") for k in ("headline", "summary"))
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text.casefold()).split())


def _numeric_column(frame: pd.DataFrame, name: str) -> pd.Series:
    if name not in frame:
        return pd.Series(float("nan"), index=frame.index, dtype=float)
    return pd.to_numeric(frame[name], errors="coerce")


def _decision_grade(events: pd.DataFrame) -> bool:
    if events.empty:
        return False
    if events["source_tier"].astype(str).isin({"official_club", "official_league"}).any():
        return True
    return bool(
        events["source_name"].astype(str).nunique() >= 2
        and events["event_fingerprint"].astype(str).nunique() >= 2
    )


def evidence_eligibility(
    players: pd.DataFrame,
    news_audit: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """Apply an EV-first evidence policy before production solves.

    Quantitative uncertainty is recorded, not converted into a second minutes penalty.
    Only official adverse status, genuinely corroborated negative evidence, or an
    unresolved positive/negative contradiction can remove XI/captain eligibility.
    Squad and bench eligibility are never removed by ordinary forecast uncertainty.
    """
    out = players.copy()
    out["evidence_state"] = "stable_silence"
    minutes = _numeric_column(out, "minutes_confidence").fillna(0)
    roles = _numeric_column(out, "role_confidence").fillna(0)
    uncertain = minutes.lt(0.75) | roles.lt(0.65)
    xi_ok = pd.Series(True, index=out.index)
    reasons: dict[int, list[str]] = {}
    uncertainty_ids: list[int] = []

    audit = news_audit.copy()
    if not audit.empty and "eligible_for_projection" in audit:
        audit = audit[audit["eligible_for_projection"].eq(True)].copy()  # noqa: E712
        audit = audit[audit["source_tier"].astype(str).isin(TRUSTED_SOURCE_TIERS)]
        audit["event_fingerprint"] = audit.apply(_normalise_event, axis=1)
    for idx, row in out.iterrows():
        pid = int(row["player_id"])
        official_status = str(row.get("status") or "a").casefold()
        official_chance = pd.to_numeric(
            pd.Series([row.get("chance_of_playing_next_round")]), errors="coerce"
        ).iloc[0]
        official_adverse = official_status in {"i", "s", "u", "n"} or (
            pd.notna(official_chance) and float(official_chance) <= 25.0
        )
        events = (
            audit[pd.to_numeric(audit.get("player_id"), errors="coerce").eq(pid)]
            if not audit.empty else audit
        )
        negative_events = events[_numeric_column(events, "multiplier").lt(1.0)]
        positive_events = events[
            _numeric_column(events, "minutes_delta").gt(0)
            | _numeric_column(events, "start_probability_delta").gt(0)
        ]
        role_events = events[
            events.get("evidence_type", pd.Series("", index=events.index))
            .astype(str)
            .isin({"availability", "manager", "role"})
        ]
        negative_supported = _decision_grade(negative_events)
        positive_supported = _decision_grade(positive_events)
        role_supported = _decision_grade(role_events)
        if official_adverse:
            xi_ok.loc[idx] = False
            out.loc[idx, "evidence_state"] = "official_adverse_status"
            reasons[pid] = ["official FPL adverse status/chance ceiling"]
        elif negative_supported and positive_supported:
            xi_ok.loc[idx] = False
            out.loc[idx, "evidence_state"] = "unresolved_contradiction"
            reasons[pid] = ["current positive and negative evidence conflict"]
        elif negative_supported:
            xi_ok.loc[idx] = False
            out.loc[idx, "evidence_state"] = "credible_negative"
            reasons[pid] = ["current decision-grade negative evidence"]
        elif uncertain.loc[idx]:
            uncertainty_ids.append(pid)
            out.loc[idx, "evidence_state"] = (
                "uncertain_supported" if role_supported else "uncertain_unverified"
            )

    out["xi_evidence_eligible"] = xi_ok.astype(bool)
    out["captain_evidence_eligible"] = xi_ok.astype(bool)
    return out, {
        "contract": "apex-evidence-eligibility-v2",
        "policy": "adverse_evidence_only_pre_solve",
        "xi_ineligible_ids": sorted(out.loc[~xi_ok, "player_id"].astype(int).tolist()),
        "uncertainty_diagnostic_ids": sorted(uncertainty_ids),
        "captain_eligible_ids": sorted(
            out.loc[out["captain_evidence_eligible"], "player_id"].astype(int).tolist()
        ),
        "reasons": {str(k): v for k, v in sorted(reasons.items())},
    }


def captain_eligible_ids(players: pd.DataFrame) -> set[int]:
    """Return evidence-eligible captain IDs without a duplicate minutes floor."""
    if "player_id" not in players.columns:
        return set()
    d = players.drop_duplicates("player_id").copy()
    ids = pd.to_numeric(d["player_id"], errors="coerce")
    eligible = ids.notna()
    if "captain_evidence_eligible" in d:
        eligible &= d["captain_evidence_eligible"].fillna(False).astype(bool)
    return set(ids.loc[eligible].astype(int))
