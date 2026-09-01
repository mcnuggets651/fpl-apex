from __future__ import annotations

import statistics
from datetime import datetime, timezone
from typing import Any, Iterable

from apex_v2_tournament_common import (
    ALL_HORIZONS, CANONICAL_PROSPECTIVE_OBSERVATION, CHAMPION_PROVIDER, DEFAULT_MAX_AGE_HOURS,
    DNS_AFTER_CUTOFF, DNS_ARTIFACT, DNS_EXPORT_MISSING, DNS_FORECAST_STALE,
    DNS_INCOMPLETE_UNIVERSE, DNS_NO_H1, DNS_SCHEMA_INVALID, DNS_TARGET,
    DNS_TRAINING_NOT_READY, DNS_TRAINING_READY_NO_MODEL, DNS_UNQUALIFIED,
    EXPECTED_PROVIDERS, GW2_CLASSIFICATION, INTERNAL_PROVIDERS, TournamentContractError,
    INTERNAL_PROVIDER_SET, PROJECTION_PROVIDER_SET, PROSPECTIVE_NOT_READY,
    PROSPECTIVE_READY_CANDIDATE, STRATEGIC_HORIZONS, UNIVERSAL_HORIZON,
    _forecast_ids, _internal_qualification, _no_forecast_ids, _openfpl_dns,
    _parse_utc, _qualified_horizons, _scoreable_tasks, _surface_rows,
    canonical_sha256,
)

def _internal_provider_record(
    *,
    provider_id: str,
    qualification: dict[str, Any],
    surface: dict[str, Any] | None,
    season: str,
    common_snapshot_at: datetime,
    deadline: datetime,
    source_release_immutable: bool,
    artifact_sha256: str | None,
    max_age_hours: float,
) -> dict[str, Any]:
    role = str(qualification.get("role") or "")
    serve_authorized = bool(qualification.get("serve_authorized", False))
    if provider_id == CHAMPION_PROVIDER:
        if role != "CHAMPION" or serve_authorized is not True:
            raise TournamentContractError("AIrsenal champion/serving authority changed")
    elif serve_authorized:
        raise TournamentContractError(f"shadow unexpectedly serve-authorized: {provider_id}")

    qualified = _qualified_horizons(qualification)
    reasons = [str(value) for value in qualification.get("reasons") or []]
    schema_ok = isinstance(surface, dict)
    generated_at: str | None = None
    stale = False
    after_deadline = False
    temporal_reason: str | None = None
    if surface is not None:
        if str(surface.get("provider_id") or "") != provider_id:
            raise TournamentContractError(f"provider surface identity mismatch: {provider_id}")
        if str(surface.get("season") or "") not in {"", season}:
            raise TournamentContractError(f"provider season mismatch: {provider_id}")
        raw_generated = str(surface.get("generated_at") or "")
        if not raw_generated or not str(surface.get("provider_version") or ""):
            schema_ok = False
        else:
            try:
                generated = _parse_utc(raw_generated)
                generated_at = generated.isoformat()
                age = (common_snapshot_at - generated).total_seconds() / 3600.0
                stale = age > float(max_age_hours)
                after_deadline = generated >= deadline
                if age < -0.1:
                    temporal_reason = "provider generated after common snapshot"
            except Exception:
                schema_ok = False
    artifact_ok = bool(artifact_sha256 and len(str(artifact_sha256)) == 64)
    no_hindsight = bool(
        source_release_immutable
        and artifact_ok
        and schema_ok
        and generated_at
        and not stale
        and not after_deadline
        and not temporal_reason
    )
    h1_qualified = 1 in qualified
    entered = bool(h1_qualified and no_hindsight)
    dns_code = None
    dns_reasons: list[str] = []
    if not entered:
        dns_reasons = list(reasons)
        if surface is None:
            dns_code = DNS_EXPORT_MISSING
        elif not artifact_ok:
            dns_code = DNS_ARTIFACT
        elif not schema_ok or temporal_reason:
            dns_code = DNS_SCHEMA_INVALID
            if temporal_reason:
                dns_reasons.append(temporal_reason)
        elif after_deadline:
            dns_code = DNS_AFTER_CUTOFF
        elif stale:
            dns_code = DNS_FORECAST_STALE
        elif not h1_qualified:
            lower = " | ".join(reasons).lower()
            dns_code = DNS_INCOMPLETE_UNIVERSE if "incomplete forecast coverage" in lower else DNS_NO_H1
        else:
            dns_code = DNS_UNQUALIFIED

    coverage: dict[str, Any] = {}
    for horizon in ALL_HORIZONS:
        forecasts = _forecast_ids(surface or {}, horizon)
        no_forecast = _no_forecast_ids(surface or {}, horizon)
        denominator = len(forecasts) + len(no_forecast)
        coverage[str(horizon)] = {
            "forecast_rows": len(forecasts),
            "no_forecast_rows": len(no_forecast),
            "row_count": len(_surface_rows(surface or {}, horizon)),
            "qualified": horizon in qualified,
            "forecast_ratio_among_rows": (len(forecasts) / denominator) if denominator else None,
        }
    strategic = bool(entered and all(h in qualified for h in STRATEGIC_HORIZONS))
    return {
        "provider_id": provider_id,
        "source": "PRODUCTION_PRIVATE_PROVIDER_ARCHIVE",
        "role": role,
        "serve_authorized": serve_authorized,
        "production_health": qualification.get("health"),
        "production_reasons": reasons,
        "provider_version": (surface or {}).get("provider_version"),
        "generated_at": generated_at,
        "artifact_sha256": artifact_sha256,
        "no_hindsight_eligible": no_hindsight,
        "qualified_horizons": list(qualified),
        "h1": {
            "status": "ENTERED" if entered else "DNS",
            "dns_code": dns_code,
            "reasons": dns_reasons,
            "forecast_rows": len(_forecast_ids(surface or {}, 1)),
        },
        "strategic_h2_h8": {
            "status": "ENTERED" if strategic else "NOT_ENTERED",
            "qualified_horizons": [h for h in qualified if h in STRATEGIC_HORIZONS],
        },
        "coverage_by_horizon": coverage,
        "scoreable_tasks": _scoreable_tasks(surface, entered=entered, horizon=1),
    }


def _pitchside_provider_record(capture: dict[str, Any]) -> dict[str, Any]:
    surface = capture.get("surface") if isinstance(capture.get("surface"), dict) else None
    health = str(capture.get("health") or "ERROR")
    qualified = tuple(int(v) for v in capture.get("qualified_horizons") or [])
    no_hindsight = bool(
        health == "HEALTHY"
        and surface
        and str(capture.get("expected_official_hash") or "")
        == str(capture.get("current_official_hash") or "")
    )
    entered = bool(no_hindsight and 1 in qualified)
    missing = (capture.get("missing_forecastable_ids_by_horizon") or {}).get("1") or []
    dns_code = None if entered else str(capture.get("dns_code") or DNS_UNQUALIFIED)
    strategic = bool(entered and all(h in qualified for h in STRATEGIC_HORIZONS))
    return {
        "provider_id": "pitchside",
        "source": "EXTERNAL_PREDEADLINE_CAPTURE",
        "role": "SHADOW",
        "serve_authorized": False,
        "production_health": health,
        "production_reasons": capture.get("reasons") or [],
        "provider_version": (surface or {}).get("provider_version"),
        "generated_at": capture.get("generated_at"),
        "artifact_sha256": capture.get("surface_sha256"),
        "source_bundle_sha256": capture.get("source_bundle_sha256"),
        "no_hindsight_eligible": no_hindsight,
        "qualified_horizons": list(qualified),
        "forecastable_player_count": capture.get("forecastable_player_count"),
        "official_unavailable_player_count": capture.get("official_unavailable_player_count"),
        "h1": {
            "status": "ENTERED" if entered else "DNS",
            "dns_code": dns_code,
            "reasons": capture.get("reasons") or [],
            "forecast_rows": int((capture.get("forecast_counts_by_horizon") or {}).get("1", 0)),
            "missing_forecastable_players": len(missing),
            "no_forecast_expected_unavailable": int(
                (capture.get("unavailable_no_forecast_expected_by_horizon") or {}).get("1", 0)
            ),
        },
        "strategic_h2_h8": {
            "status": "ENTERED" if strategic else "NOT_ENTERED",
            "qualified_horizons": [h for h in qualified if h in STRATEGIC_HORIZONS],
        },
        "coverage_by_horizon": {
            str(h): {
                "forecast_rows": int((capture.get("forecast_counts_by_horizon") or {}).get(str(h), 0)),
                "missing_forecastable_players": len(
                    (capture.get("missing_forecastable_ids_by_horizon") or {}).get(str(h)) or []
                ),
                "no_forecast_expected_unavailable": int(
                    (capture.get("unavailable_no_forecast_expected_by_horizon") or {}).get(str(h), 0)
                ),
                "qualified": h in qualified,
            }
            for h in ALL_HORIZONS
        },
        "scoreable_tasks": _scoreable_tasks(surface, entered=entered, horizon=1),
    }


def _openfpl_provider_record(readiness: dict[str, Any] | None) -> dict[str, Any]:
    code, reasons, state = _openfpl_dns(readiness)
    return {
        "provider_id": "openfpl",
        "source": "GOVERNED_CURRENT_RULES_READINESS",
        "role": "SHADOW",
        "serve_authorized": False,
        "production_health": (readiness or {}).get("health", "UNKNOWN"),
        "production_reasons": reasons,
        "provider_version": None,
        "generated_at": None,
        "artifact_sha256": None,
        "no_hindsight_eligible": False,
        "qualified_horizons": [],
        "training_state": state,
        "exact_rule_gameweek_count": (readiness or {}).get("exact_rule_gameweek_count"),
        "minimum_exact_rule_gameweeks": (readiness or {}).get("minimum_exact_rule_gameweeks"),
        "history_commit": (readiness or {}).get("resolved_history_commit"),
        "history_manifest_sha256": (readiness or {}).get("observed_history_manifest_sha256"),
        "h1": {"status": "DNS", "dns_code": code, "reasons": reasons, "forecast_rows": 0},
        "strategic_h2_h8": {"status": "NOT_ENTERED", "qualified_horizons": []},
        "coverage_by_horizon": {str(h): {"forecast_rows": 0, "qualified": False} for h in ALL_HORIZONS},
        "scoreable_tasks": _scoreable_tasks(None, entered=False),
    }


def build_readiness(
    public_attempt: dict[str, Any],
    governance: dict[str, Any],
    internal_surfaces: dict[str, dict[str, Any]],
    *,
    source_release: dict[str, Any],
    internal_surface_sha256: dict[str, str],
    pitchside_capture: dict[str, Any],
    openfpl_readiness: dict[str, Any] | None,
    private_base_release_tag: str,
    private_tournament_release_tag: str | None,
    market_benchmark: dict[str, Any] | None = None,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
) -> dict[str, Any]:
    season = str(public_attempt.get("season") or "")
    gameweek = int(public_attempt.get("target_gameweek") or 0)
    official_hash = str(public_attempt.get("official_snapshot_sha256") or "")
    frozen_at = _parse_utc(str(public_attempt.get("frozen_at") or ""))
    certification = public_attempt.get("certification") or {}
    deadline = _parse_utc(str(certification.get("valid_until") or ""))
    if not season or gameweek <= 0 or len(official_hash) != 64:
        raise TournamentContractError("public attempt lacks tournament authority fields")
    if frozen_at >= deadline:
        raise TournamentContractError("source production seal is not predeadline")
    if source_release.get("immutable") is not True:
        raise TournamentContractError("source production release is not immutable")

    internal_q = _internal_qualification(governance)
    records: dict[str, dict[str, Any]] = {}
    for pid in INTERNAL_PROVIDERS:
        records[pid] = _internal_provider_record(
            provider_id=pid,
            qualification=internal_q[pid],
            surface=internal_surfaces.get(pid),
            season=season,
            common_snapshot_at=frozen_at,
            deadline=deadline,
            source_release_immutable=True,
            artifact_sha256=internal_surface_sha256.get(pid),
            max_age_hours=max_age_hours,
        )
    records["pitchside"] = _pitchside_provider_record(pitchside_capture)
    records["openfpl"] = _openfpl_provider_record(openfpl_readiness)
    if set(records) != PROJECTION_PROVIDER_SET:
        raise TournamentContractError("not every required tournament provider is explicitly accounted for")

    universal = [pid for pid in EXPECTED_PROVIDERS if records[pid]["h1"]["status"] == "ENTERED"]
    strategic = [pid for pid in EXPECTED_PROVIDERS if records[pid]["strategic_h2_h8"]["status"] == "ENTERED"]
    dns = {
        pid: {"dns_code": records[pid]["h1"].get("dns_code"), "reasons": records[pid]["h1"].get("reasons") or []}
        for pid in EXPECTED_PROVIDERS
        if records[pid]["h1"]["status"] == "DNS"
    }
    production_actionable = bool(certification.get("actionable")) and bool(
        (public_attempt.get("manager_actionability") or {}).get("personalized_actionable")
    )
    serving = public_attempt.get("serving_provider_by_horizon") or {}
    serving_unchanged = all(
        str(serving.get(str(h), serving.get(h, ""))) == CHAMPION_PROVIDER for h in ALL_HORIZONS
    )
    if not serving_unchanged:
        raise TournamentContractError("production serving map changed away from AIrsenal H1-H8")
    champion_entered = CHAMPION_PROVIDER in universal
    challenger_entered = any(pid != CHAMPION_PROVIDER for pid in universal)
    evaluator_scoreable = bool(universal) and all(records[pid]["scoreable_tasks"]["player_xp"] for pid in universal)

    market = market_benchmark or {
        "category": "MARKET_BENCHMARK",
        "status": "UNAVAILABLE",
        "projection_league_entrant": False,
        "reasons": ["repository search found no immutable predeadline market benchmark artifact"],
    }
    if market.get("projection_league_entrant") is True:
        raise TournamentContractError("market benchmark cannot masquerade as player projection entrant")

    exact_common_hash = (
        str(pitchside_capture.get("expected_official_hash") or "") == official_hash
        and str(pitchside_capture.get("current_official_hash") or "") == official_hash
    )
    ready = bool(
        gameweek >= 3
        and production_actionable
        and champion_entered
        and challenger_entered
        and evaluator_scoreable
        and exact_common_hash
    )
    blockers = []
    if not production_actionable:
        blockers.append("independent production recommendation is not actionable")
    if not champion_entered:
        blockers.append("AIrsenal champion is not a valid H1 tournament entrant")
    if not challenger_entered:
        blockers.append("no challenger has a valid H1 tournament entry")
    if not evaluator_scoreable:
        blockers.append("entered H1 providers are not scoreable")
    if not exact_common_hash:
        blockers.append("external capture is not bound to the exact production Official hash")

    classification = PROSPECTIVE_READY_CANDIDATE if ready else PROSPECTIVE_NOT_READY
    if gameweek == 2:
        classification = GW2_CLASSIFICATION
        ready = False
        blockers.append("GW2 is retained as diagnostic/rehearsal evidence only")

    payload = {
        "schema_version": 2,
        "contract": "APEX_V2_PROSPECTIVE_TOURNAMENT_V2",
        "production_influence": "NONE",
        "promotion_authority": False,
        "automatic_promotion": False,
        "season": season,
        "target_gameweek": gameweek,
        "classification": classification,
        "prospective_observation_number": None,
        "tournament_ready": ready,
        "common_seal": {
            "public_attempt_id": public_attempt.get("public_attempt_id"),
            "run_id": public_attempt.get("run_id"),
            "snapshot_id": public_attempt.get("snapshot_id"),
            "snapshot_frozen_at": frozen_at.isoformat(),
            "official_snapshot_sha256": official_hash,
            "external_capture_official_sha256": pitchside_capture.get("current_official_hash"),
            "deadline": deadline.isoformat(),
            "source_release_tag": source_release.get("tag_name"),
            "source_release_id": source_release.get("id"),
            "source_release_immutable": True,
            "private_base_release_tag": private_base_release_tag,
            "private_tournament_release_tag": private_tournament_release_tag,
            "eligible_common_predeadline_candidate": True,
            "canonical_last_valid_predeadline": False,
        },
        "production": {
            "independently_actionable": production_actionable,
            "serving_provider_by_horizon": serving,
            "serving_architecture_unchanged": serving_unchanged,
        },
        "providers": records,
        "universal_h1_league": {
            "entrants": universal,
            "dns": dns,
            "evaluator_scoreable": evaluator_scoreable,
        },
        "strategic_horizon_league": {
            "required_horizons": list(STRATEGIC_HORIZONS),
            "entrants": strategic,
            "partial_or_dns": [pid for pid in EXPECTED_PROVIDERS if pid not in strategic],
            "scoring_policy": "EACH_HORIZON_SCORED_ONLY_AFTER_ITS_REALIZED_GAMEWEEK_FINISHES",
        },
        "market_benchmark": market,
        "readiness_blockers": blockers,
        "gw2_policy": {
            "classification": GW2_CLASSIFICATION,
            "retain_diagnostic_evidence": True,
            "canonical_win_loss_allowed": False,
            "promotion_demotion_allowed": False,
        },
        "evaluation_policy": {
            "sealed_forecasts_only": True,
            "post_deadline_regeneration_forbidden": True,
            "forecast_quality_separate_from_decision_quality": True,
            "decision_quality_release_prefix": "apex-v2/private-decision-quality",
            "specialist_metrics_only_when_both_sealed_prediction_and_realized_label_exist": True,
        },
    }
    payload["readiness_sha256"] = canonical_sha256(payload)
    return payload


def select_latest_valid_common_seal(
    candidates: Iterable[dict[str, Any]],
    *,
    gameweek: int,
    as_of: datetime | None = None,
    require_cutoff_passed: bool = False,
) -> dict[str, Any] | None:
    eligible = []
    for candidate in candidates:
        if int(candidate.get("target_gameweek", -1)) != int(gameweek):
            continue
        if candidate.get("tournament_ready") is not True:
            continue
        seal = candidate.get("common_seal") or {}
        try:
            frozen = _parse_utc(str(seal["snapshot_frozen_at"]))
            deadline = _parse_utc(str(seal["deadline"]))
        except Exception:
            continue
        if frozen >= deadline or seal.get("source_release_immutable") is not True:
            continue
        eligible.append(candidate)
    if not eligible:
        return None
    selected = max(
        eligible,
        key=lambda row: _parse_utc(str((row.get("common_seal") or {})["snapshot_frozen_at"])),
    )
    if require_cutoff_passed:
        when = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
        deadline = _parse_utc(str((selected.get("common_seal") or {})["deadline"]))
        if when < deadline:
            return None
    return selected


def canonicalize_selected_observation(
    selected: dict[str, Any],
    *,
    observation_number: int,
    selected_at: datetime | None = None,
) -> dict[str, Any]:
    if selected.get("tournament_ready") is not True:
        raise TournamentContractError("cannot canonicalize non-ready candidate")
    if int(observation_number) < 1:
        raise TournamentContractError("observation number must be >=1")
    seal = selected.get("common_seal") or {}
    frozen = _parse_utc(str(seal.get("snapshot_frozen_at") or ""))
    deadline = _parse_utc(str(seal.get("deadline") or ""))
    when = (selected_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if when < deadline:
        raise TournamentContractError("cannot canonicalize before Official deadline")
    if frozen >= deadline:
        raise TournamentContractError("selected candidate is not predeadline")
    output = {
        "schema_version": 1,
        "contract": "APEX_V2_CANONICAL_PROSPECTIVE_SELECTION_V1",
        "production_influence": "NONE",
        "promotion_authority": False,
        "classification": CANONICAL_PROSPECTIVE_OBSERVATION,
        "prospective_observation_number": int(observation_number),
        "season": selected.get("season"),
        "target_gameweek": int(selected.get("target_gameweek")),
        "selected_at": when.isoformat(),
        "selection_rule": "LAST_VALID_COMMON_PREDEADLINE_SEAL",
        "selected_readiness_sha256": selected.get("readiness_sha256"),
        "selected_candidate_tag": (selected.get("common_seal") or {}).get("candidate_release_tag"),
        "selected_common_seal": seal,
    }
    output["selection_sha256"] = canonical_sha256(output)
    return output


def reliability_summary(readiness_payloads: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in readiness_payloads if int(row.get("target_gameweek", 0)) >= 2]
    providers: dict[str, Any] = {}
    for pid in EXPECTED_PROVIDERS:
        attempts = 0
        entered = 0
        dns: dict[str, int] = {}
        ages = []
        for payload in rows:
            record = (payload.get("providers") or {}).get(pid)
            if not isinstance(record, dict):
                continue
            attempts += 1
            h1 = record.get("h1") or {}
            if h1.get("status") == "ENTERED":
                entered += 1
            else:
                code = str(h1.get("dns_code") or "UNKNOWN")
                dns[code] = dns.get(code, 0) + 1
            generated = record.get("generated_at")
            frozen = (payload.get("common_seal") or {}).get("snapshot_frozen_at")
            if generated and frozen:
                try:
                    ages.append(
                        (_parse_utc(str(frozen)) - _parse_utc(str(generated))).total_seconds()
                        / 3600.0
                    )
                except Exception:
                    pass
        providers[pid] = {
            "attempts": attempts,
            "successful_h1_submissions": entered,
            "submission_rate": entered / attempts if attempts else None,
            "dns_counts": dns,
            "mean_age_at_common_seal_hours": statistics.fmean(ages) if ages else None,
        }
    return {
        "schema_version": 1,
        "contract": "APEX_V2_PROVIDER_RELIABILITY_V1",
        "production_influence": "NONE",
        "candidate_count": len(rows),
        "providers": providers,
    }
