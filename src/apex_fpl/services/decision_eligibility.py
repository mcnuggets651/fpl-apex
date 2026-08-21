from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from apex_fpl.data.news import TRUSTED_SOURCE_TIERS
from apex_fpl.services.player_identity import resolve_source_identities
from apex_fpl.services.specialist_disagreement import SPECIALIST_SOURCES, build_specialist_disagreement_report

MIN_CAPTAIN_EXPECTED_MINUTES = 0.0
MIN_CAPTAIN_START_PROBABILITY = 0.0
MIN_CAPTAIN_APPEARANCE_PROBABILITY = 0.0
MIN_CAPTAIN_PROJECTION_CONFIDENCE = 0.0
MIN_SOURCE_HEALTH_RATIO = 2 / 3
MIN_HEALTHY_NEWS_SOURCES = 2
MIN_FRESH_NEWS_ITEMS = 1
SOURCE_HEALTH_WINDOW_HOURS = 120.0
DEFAULT_SPECIALIST_PREDICTIONS = Path("data/manual/specialist_predictions.csv")
DEFAULT_SQUAD_HIERARCHY = Path("data/manual/squad_hierarchy.csv")
MATERIAL_SPECIALIST_CONTRADICTION_START_PROBABILITY = 0.80
WEAK_SQUAD_HIERARCHY = {"academy", "u21", "youth", "fringe", "reserve"}


def source_health_status(sources: list) -> dict:
    row = next((s for s in sources if getattr(s, "name", "") == "news_source_health"), None)
    try:
        measured = json.loads(getattr(row, "version", "") or "{}")
    except json.JSONDecodeError:
        measured = {}
    configured = int(measured.get("configured_sources", 0) or 0)
    healthy = int(measured.get("healthy_sources", 0) or 0)
    fresh = int(measured.get("fresh_timestamped_items", 0) or 0)
    ratio = healthy / configured if configured else 0.0
    ready = bool(configured >= 2 and healthy >= MIN_HEALTHY_NEWS_SOURCES and ratio >= MIN_SOURCE_HEALTH_RATIO and fresh >= MIN_FRESH_NEWS_ITEMS)
    return {"contract": "apex-news-source-health-v1", "ready": ready, "configured_sources": configured, "healthy_sources": healthy, "healthy_ratio": ratio, "fresh_timestamped_items": fresh, "window_hours": SOURCE_HEALTH_WINDOW_HOURS, "minimum_healthy_sources": MIN_HEALTHY_NEWS_SOURCES, "minimum_healthy_ratio": MIN_SOURCE_HEALTH_RATIO, "minimum_fresh_timestamped_items": MIN_FRESH_NEWS_ITEMS}


def _normalise_event(row: pd.Series) -> str:
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
    return bool(events["source_name"].astype(str).nunique() >= 2 and events["event_fingerprint"].astype(str).nunique() >= 2)


def _fresh_specialist_predictions(players: pd.DataFrame, path: Path, *, now: datetime | None = None, strict_identity: bool = True) -> pd.DataFrame:
    columns = {"player_id", "source_player_name", "source", "predicted_start", "published_at", "retrieved_at", "expires_at"}
    if not path.exists():
        return pd.DataFrame(columns=sorted(columns))
    frame = pd.read_csv(path)
    missing = columns - set(frame.columns)
    if missing:
        raise ValueError(f"{path} missing governed specialist evidence columns: {sorted(missing)}")
    current = pd.Timestamp(now or datetime.now(timezone.utc))
    current = current.tz_localize("UTC") if current.tzinfo is None else current.tz_convert("UTC")
    published = pd.to_datetime(frame["published_at"], utc=True, errors="coerce")
    retrieved = pd.to_datetime(frame["retrieved_at"], utc=True, errors="coerce")
    expires = pd.to_datetime(frame["expires_at"], utc=True, errors="coerce")
    invalid = published.isna() | retrieved.isna() | expires.isna() | (expires <= published)
    if invalid.any():
        if strict_identity:
            raise ValueError("governed specialist evidence has invalid timestamps")
        frame = frame.loc[~invalid].copy()
        expires = expires.loc[~invalid]
    frame = frame.loc[current <= expires].copy()
    if frame.empty:
        return frame
    if not strict_identity:
        official_names = {int(row.player_id): str(row.web_name).strip().casefold() for row in players.itertuples(index=False) if hasattr(row, "web_name")}
        frame = frame[frame.apply(lambda row: official_names.get(int(row["player_id"])) == str(row["source_player_name"]).strip().casefold(), axis=1)].copy()
        if frame.empty:
            return frame
    frame, identity = resolve_source_identities(players, frame, source="fpl_specialist_presolve", name_columns=("source_player_name",), allow_name_fallback=False, require_identity_witness=True, raise_on_error=False)
    if not identity.ready:
        raise ValueError("specialist pre-solve identity failed: " + "; ".join(identity.blockers[:10]))
    frame["source"] = frame["source"].astype(str).str.strip().str.casefold()
    frame = frame[frame["source"].isin(SPECIALIST_SOURCES)].copy()
    frame["predicted_start"] = frame["predicted_start"].astype(str).str.strip().str.casefold().map({"true": True, "1": True, "yes": True, "start": True, "false": False, "0": False, "no": False, "bench": False})
    if frame["predicted_start"].isna().any():
        raise ValueError("specialist predicted_start must be boolean/start/bench")
    return frame


def _fresh_squad_hierarchy(players: pd.DataFrame, path: Path, *, now: datetime | None = None, strict_identity: bool = True) -> pd.DataFrame:
    required = {"player_id", "hierarchy_status", "valid_until"}
    if not path.exists():
        return pd.DataFrame(columns=sorted(required | {"web_name"}))
    frame = pd.read_csv(path)
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{path} missing governed hierarchy columns: {sorted(missing)}")
    name_col = "source_player_name" if "source_player_name" in frame.columns else "web_name" if "web_name" in frame.columns else None
    if name_col is None:
        raise ValueError(f"{path} requires an independent player-name witness")
    current = pd.Timestamp(now or datetime.now(timezone.utc))
    current = current.tz_localize("UTC") if current.tzinfo is None else current.tz_convert("UTC")
    expiry = pd.to_datetime(frame["valid_until"], utc=True, errors="coerce")
    invalid = expiry.isna()
    if invalid.any():
        if strict_identity:
            raise ValueError("governed squad hierarchy has invalid valid_until timestamps")
        frame = frame.loc[~invalid].copy()
        expiry = expiry.loc[~invalid]
    frame = frame.loc[current <= expiry].copy()
    if frame.empty:
        return frame
    if not strict_identity:
        official_names = {int(row.player_id): str(row.web_name).strip().casefold() for row in players.itertuples(index=False) if hasattr(row, "web_name")}
        frame = frame[frame.apply(lambda row: official_names.get(int(row["player_id"])) == str(row[name_col]).strip().casefold(), axis=1)].copy()
        if frame.empty:
            return frame
    frame, identity = resolve_source_identities(players, frame, source="squad_hierarchy_presolve", name_columns=(name_col,), allow_name_fallback=False, require_identity_witness=True, raise_on_error=False)
    if not identity.ready:
        raise ValueError("squad hierarchy pre-solve identity failed: " + "; ".join(identity.blockers[:10]))
    frame["hierarchy_status"] = frame["hierarchy_status"].astype(str).str.strip().str.casefold()
    return frame


def evidence_eligibility(players: pd.DataFrame, news_audit: pd.DataFrame, *, specialist_predictions_path: Path | None = None, squad_hierarchy_path: Path | None = None, now: datetime | None = None) -> tuple[pd.DataFrame, dict]:
    """Apply governed football-state eligibility before production solves without rewriting xP."""
    out = players.copy()
    out["evidence_state"] = "stable_silence"
    minutes = _numeric_column(out, "minutes_confidence").fillna(0)
    roles = _numeric_column(out, "role_confidence").fillna(0)
    uncertain = minutes.lt(0.75) | roles.lt(0.65)
    xi_ok = pd.Series(True, index=out.index)
    squad_ok = pd.Series(True, index=out.index)
    reasons: dict[int, list[str]] = {}
    uncertainty_ids: list[int] = []
    audit = news_audit.copy()
    if not audit.empty and "eligible_for_projection" in audit:
        audit = audit[audit["eligible_for_projection"].eq(True)].copy()  # noqa: E712
        audit = audit[audit["source_tier"].astype(str).isin(TRUSTED_SOURCE_TIERS)]
        audit["event_fingerprint"] = audit.apply(_normalise_event, axis=1)
    authoritative_positive: set[int] = set()
    for idx, row in out.iterrows():
        pid = int(row["player_id"])
        official_status = str(row.get("status") or "a").casefold()
        official_chance = pd.to_numeric(pd.Series([row.get("chance_of_playing_next_round")]), errors="coerce").iloc[0]
        official_adverse = official_status in {"i", "s", "u", "n"} or (pd.notna(official_chance) and float(official_chance) <= 25.0)
        events = audit[pd.to_numeric(audit.get("player_id"), errors="coerce").eq(pid)] if not audit.empty else audit
        negative_events = events[_numeric_column(events, "multiplier").lt(1.0)]
        positive_events = events[_numeric_column(events, "minutes_delta").gt(0) | _numeric_column(events, "start_probability_delta").gt(0)]
        role_events = events[events.get("evidence_type", pd.Series("", index=events.index)).astype(str).isin({"availability", "manager", "role"})]
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
        elif positive_supported:
            authoritative_positive.add(pid)
            out.loc[idx, "evidence_state"] = "credible_positive"
        elif uncertain.loc[idx]:
            uncertainty_ids.append(pid)
            out.loc[idx, "evidence_state"] = "uncertain_supported" if role_supported else "uncertain_unverified"

    hierarchy_path = Path(squad_hierarchy_path) if squad_hierarchy_path is not None else DEFAULT_SQUAD_HIERARCHY
    hierarchy = _fresh_squad_hierarchy(out, hierarchy_path, now=now, strict_identity=squad_hierarchy_path is not None)
    if not hierarchy.empty:
        for row in hierarchy.itertuples(index=False):
            pid = int(row.player_id)
            status = str(row.hierarchy_status).strip().casefold()
            if status in WEAK_SQUAD_HIERARCHY:
                mask = out["player_id"].astype(int).eq(pid)
                squad_ok.loc[mask] = False
                xi_ok.loc[mask] = False
                out.loc[mask, "evidence_state"] = "authoritative_weak_squad_hierarchy"
                reasons.setdefault(pid, []).append(f"current governed squad hierarchy is {status}; excluded from production squad pre-solve")

    specialist_path = Path(specialist_predictions_path) if specialist_predictions_path is not None else DEFAULT_SPECIALIST_PREDICTIONS
    specialist = _fresh_specialist_predictions(out, specialist_path, now=now, strict_identity=specialist_predictions_path is not None)
    specialist_report = build_specialist_disagreement_report(out, specialist)
    if not specialist_report.empty:
        for row in specialist_report.itertuples(index=False):
            pid = int(row.player_id)
            if int(row.specialist_source_count) >= 2 and str(row.specialist_consensus) == "bench" and pid not in authoritative_positive:
                mask = out["player_id"].astype(int).eq(pid)
                model_start = pd.to_numeric(out.loc[mask, "start_probability"], errors="coerce").fillna(0.0)
                material_contradiction = bool((model_start >= MATERIAL_SPECIALIST_CONTRADICTION_START_PROBABILITY).any())
                if material_contradiction:
                    xi_ok.loc[mask] = False
                    out.loc[mask, "evidence_state"] = "specialist_nonstart_material_xi_constraint"
                    reasons.setdefault(pid, []).append("fresh two-source governed non-start consensus materially contradicts model start probability; XI eligibility removed pre-solve")
                else:
                    out.loc[mask, "evidence_state"] = "specialist_nonstart_diagnostic"
                    reasons.setdefault(pid, []).append("fresh two-source governed non-start consensus recorded below hard-constraint contradiction threshold")
    out["squad_evidence_eligible"] = squad_ok.astype(bool)
    out["xi_evidence_eligible"] = xi_ok.astype(bool)
    out["captain_evidence_eligible"] = xi_ok.astype(bool)
    report = {"contract": "apex-evidence-eligibility-v2", "policy_version": 4, "policy": "authoritative_adverse_plus_governed_hierarchy_squad_constraint_plus_material_specialist_xi_constraint_pre_solve", "squad_ineligible_ids": sorted(out.loc[~squad_ok, "player_id"].astype(int).tolist()), "xi_ineligible_ids": sorted(out.loc[~xi_ok, "player_id"].astype(int).tolist()), "uncertainty_diagnostic_ids": sorted(uncertainty_ids), "captain_eligible_ids": sorted(out.loc[out["captain_evidence_eligible"], "player_id"].astype(int).tolist()), "reasons": {str(k): v for k, v in sorted(reasons.items())}}
    if not specialist_report.empty:
        report["specialist_consensus"] = {str(int(row.player_id)): str(row.specialist_consensus) for row in specialist_report.itertuples(index=False) if int(row.specialist_source_count) > 0}
    return out.reset_index(drop=True), report


def captain_eligible_ids(players: pd.DataFrame) -> set[int]:
    if "player_id" not in players.columns:
        return set()
    d = players.drop_duplicates("player_id").copy()
    ids = pd.to_numeric(d["player_id"], errors="coerce")
    eligible = ids.notna()
    if "captain_evidence_eligible" in d:
        eligible &= d["captain_evidence_eligible"].fillna(False).astype(bool)
    return set(ids.loc[eligible].astype(int))
