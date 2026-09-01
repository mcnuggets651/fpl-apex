#!/usr/bin/env python3
"""Operations-only reliability boundary for non-serving Apex shadow providers.

This controller is materialised from the control-plane SHA while the Apex V2
engine remains checked out at its frozen SHA. It never grants serving authority,
changes projections, reads manager credentials, invokes the solver, or backfills
provider forecasts. Its job is to make provider availability and provenance
explicit, resilient to transient infrastructure failures, and hindsight-safe.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
import yaml

EXTERNAL_DIAGNOSTIC_IDS = ("pitchside", "openfpl")
PRODUCTION_INFLUENCE = "NONE"
PITCHSIDE_BASE = "https://bjarkisigur7.github.io/fpl-ai-assistant/data"
FPL_BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_FIXTURES = "https://fantasy.premierleague.com/api/fixtures/"
GITHUB_API = "https://api.github.com"
OPENFPL_MIN_GAMEWEEKS = 10
GW_FILE_RE = re.compile(r"^gw(\d+)\.csv$")

DASTAN_TRANSIENT_PATTERNS = (
    "could not resolve host",
    "temporary failure in name resolution",
    "name or service not known",
    "network is unreachable",
    "connection reset",
    "connection refused",
    "connection aborted",
    "failed to establish a new connection",
    "remote end hung up",
    "early eof",
    "read timed out",
    "connect timeout",
    "connection timeout",
    "tls handshake",
    "ssl error",
    "http 408",
    "http 429",
    "http 500",
    "http 502",
    "http 503",
    "http 504",
    "status 408",
    "status 429",
    "status 500",
    "status 502",
    "status 503",
    "status 504",
    "pypi.org",
    "files.pythonhosted.org",
)


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_json(payload: Any) -> str:
    return _sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _source(lock: dict[str, Any], key: str) -> dict[str, Any]:
    source = (lock.get("sources") or {}).get(key)
    if not isinstance(source, dict) or not source.get("repository") or not source.get("commit"):
        raise ValueError(f"frozen upstream lock missing required source {key}")
    return source


def derive_runtime_config(source: Path, output: Path, report: Path) -> dict[str, Any]:
    """Exclude external diagnostics from frozen production qualification only."""
    raw = source.read_bytes()
    cfg = yaml.safe_load(raw)
    if not isinstance(cfg, dict) or not isinstance(cfg.get("providers"), list):
        raise ValueError("invalid Apex V2 config")

    providers = cfg["providers"]
    by_id = {str(p.get("id")): p for p in providers}
    if set(EXTERNAL_DIAGNOSTIC_IDS) - set(by_id):
        raise ValueError("frozen config missing expected external diagnostics")
    champion = by_id.get("airsenal")
    if not champion or champion.get("role") != "CHAMPION" or champion.get("serve_authorized") is not True:
        raise ValueError("AIrsenal serving-champion invariant failed")
    if tuple(champion.get("requested_horizons") or ()) != tuple(range(1, 9)):
        raise ValueError("AIrsenal H1-H8 serving horizon invariant failed")

    removed: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    for provider in providers:
        pid = str(provider.get("id"))
        if pid in EXTERNAL_DIAGNOSTIC_IDS:
            if provider.get("serve_authorized") is not False:
                raise ValueError(f"refusing to externalise serving-authorized provider {pid}")
            removed.append(provider)
        else:
            kept.append(provider)
    cfg["providers"] = kept

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    report_payload = {
        "schema_version": 2,
        "mode": "EXTERNAL_DIAGNOSTIC_BOUNDARY",
        "production_influence": PRODUCTION_INFLUENCE,
        "frozen_config_sha256": _sha256_bytes(raw),
        "runtime_config_sha256": _sha256_bytes(output.read_bytes()),
        "removed_from_production_qualification": [str(p["id"]) for p in removed],
        "retained_shadow_providers": [str(p["id"]) for p in kept if str(p.get("role")) == "SHADOW"],
        "serving_provider": "airsenal",
        "serving_horizons": list(range(1, 9)),
        "auto_promotion": False,
        "blending": False,
        "reason": (
            "PITCHSIDE and OpenFPL are non-serving external diagnostics; their "
            "availability must not change production certification or decisions."
        ),
    }
    _atomic_json(report, report_payload)
    return report_payload


@dataclass
class RetryHttp:
    session: Any
    attempts: int = 4
    timeout: float = 20.0
    base_sleep: float = 0.35

    def get(self, url: str) -> Any:
        last: Exception | None = None
        for attempt in range(1, self.attempts + 1):
            try:
                response = self.session.get(url, timeout=self.timeout)
                status = int(response.status_code)
                if status == 429 or status >= 500 or status == 408:
                    if attempt == self.attempts:
                        response.raise_for_status()
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else self.base_sleep * (2 ** (attempt - 1))
                    time.sleep(delay + random.uniform(0.0, min(0.15, delay / 4)))
                    continue
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status is not None and 400 <= int(status) < 500 and int(status) not in {408, 429}:
                    raise
                if attempt == self.attempts:
                    raise
                time.sleep(self.base_sleep * (2 ** (attempt - 1)))
        raise RuntimeError(f"HTTP retry exhausted: {last}")


def _json_response(client: RetryHttp, url: str) -> tuple[bytes, Any]:
    response = client.get(url)
    raw = bytes(response.content)
    return raw, response.json()


def _official_public(client: RetryHttp, now: datetime) -> dict[str, Any]:
    raw_bootstrap, bootstrap = _json_response(client, FPL_BOOTSTRAP)
    raw_fixtures, fixtures = _json_response(client, FPL_FIXTURES)
    if not isinstance(bootstrap, dict) or not isinstance(fixtures, list):
        raise ValueError("Official FPL public payload shape invalid")
    future = []
    for event in bootstrap.get("events") or []:
        deadline = event.get("deadline_time")
        if deadline and _utc(deadline) > now:
            future.append(int(event["id"]))
    if not future:
        raise ValueError("no future Official FPL deadline")
    target = min(future)
    completed = sorted(
        int(event["id"])
        for event in bootstrap.get("events") or []
        if event.get("id") is not None
        and int(event["id"]) < target
        and event.get("finished") is True
        and event.get("data_checked") is True
    )
    digest = hashlib.sha256()
    digest.update(raw_bootstrap)
    digest.update(b"\0")
    digest.update(raw_fixtures)
    return {
        "target_gameweek": target,
        "completed_gameweeks": completed,
        "elements": bootstrap.get("elements") or [],
        "public_payload_sha256": digest.hexdigest(),
    }


def pitchside_health(
    *,
    report: Path,
    now: datetime | None = None,
    session: Any = None,
    max_age_hours: float = 18.0,
) -> dict[str, Any]:
    """Audit PITCHSIDE without backfilling unavailable Official identities."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    client = RetryHttp(session or requests.Session())
    result: dict[str, Any] = {
        "schema_version": 2,
        "provider_id": "pitchside",
        "role": "EXTERNAL_DIAGNOSTIC",
        "serve_authorized": False,
        "production_influence": PRODUCTION_INFLUENCE,
        "checked_at": now.isoformat(),
        "source_base_url": PITCHSIDE_BASE,
    }
    try:
        official = _official_public(client, now)
        raw_meta, meta = _json_response(client, f"{PITCHSIDE_BASE}/meta.json")
        raw_xp, xp = _json_response(client, f"{PITCHSIDE_BASE}/xp.json")
        raw_players, players = _json_response(client, f"{PITCHSIDE_BASE}/players.json")
        raw_meta_after, meta_after = _json_response(client, f"{PITCHSIDE_BASE}/meta.json")
        if raw_meta_after != raw_meta or meta_after != meta:
            raise ValueError("PITCHSIDE bundle changed during acquisition")
        if not isinstance(meta, dict) or not isinstance(xp, dict) or not isinstance(players, list):
            raise ValueError("PITCHSIDE public bundle schema invalid")

        generated_at = str(meta.get("generated_utc") or "")
        if not generated_at:
            raise ValueError("PITCHSIDE generated_utc missing")
        generated = _utc(generated_at)
        age = (now - generated).total_seconds() / 3600.0
        gws = [int(v) for v in xp.get("gws") or []]
        forecasts = xp.get("players")
        if not isinstance(forecasts, dict):
            raise ValueError("PITCHSIDE xp.players must be an object")
        target = int(official["target_gameweek"])
        if target not in gws:
            raise ValueError(f"PITCHSIDE has no forecast for target GW{target}")
        idx = gws.index(target)

        elements = [e for e in official["elements"] if e.get("id") is not None]
        all_ids = {int(e["id"]) for e in elements}
        unavailable_ids = {int(e["id"]) for e in elements if str(e.get("status") or "") == "u"}
        decision_ids = all_ids - unavailable_ids
        code_to_element = {
            int(e["code"]): int(e["id"])
            for e in elements
            if e.get("code") is not None
        }
        pitchside_codes = {
            int(p["player_code"])
            for p in players
            if isinstance(p, dict) and p.get("player_code") is not None
        }
        official_codes = set(code_to_element)
        missing_roster_codes = sorted(official_codes - pitchside_codes)

        forecast_ids: set[int] = set()
        malformed_target_ids: set[int] = set()
        for raw_code, vector in forecasts.items():
            try:
                code = int(raw_code)
            except (TypeError, ValueError):
                continue
            element_id = code_to_element.get(code)
            if element_id is None:
                continue
            if not isinstance(vector, list) or idx >= len(vector):
                malformed_target_ids.add(element_id)
                continue
            value = vector[idx]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                if value is not None:
                    malformed_target_ids.add(element_id)
                continue
            forecast_ids.add(element_id)

        missing_full = sorted(all_ids - forecast_ids)
        missing_decision = sorted(decision_ids - forecast_ids)
        forecasted_unavailable = sorted(unavailable_ids & forecast_ids)
        forecast_codes = {
            int(c) for c in forecasts if str(c).lstrip("-").isdigit()
        }
        covered_horizons: list[int] = []
        for horizon in range(1, 9):
            gw = target + horizon - 1
            if gw not in gws:
                continue
            hidx = gws.index(gw)
            complete = True
            if any(code not in forecast_codes for code, eid in code_to_element.items() if eid in decision_ids):
                complete = False
            if complete:
                for raw_code, vector in forecasts.items():
                    try:
                        code = int(raw_code)
                    except (TypeError, ValueError):
                        continue
                    eid = code_to_element.get(code)
                    if eid not in decision_ids:
                        continue
                    if not isinstance(vector, list) or hidx >= len(vector):
                        complete = False
                        break
                    value = vector[hidx]
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        complete = False
                        break
            if complete:
                covered_horizons.append(horizon)

        state = "HEALTHY"
        reasons: list[str] = []
        if age < -0.1:
            state = "ERROR"
            reasons.append(f"source timestamp is {-age:.2f}h in the future")
        elif age > max_age_hours:
            state = "STALE"
            reasons.append(f"source age {age:.2f}h exceeds {max_age_hours:.2f}h")
        if missing_roster_codes:
            state = "INCOMPLETE" if state == "HEALTHY" else state
            reasons.append(f"players.json missing {len(missing_roster_codes)} Official player codes")
        if malformed_target_ids:
            state = "INCOMPLETE" if state == "HEALTHY" else state
            reasons.append(f"target GW contains malformed forecasts for {len(malformed_target_ids)} Official players")
        if missing_decision:
            state = "INCOMPLETE" if state == "HEALTHY" else state
            reasons.append(f"target GW forecast missing for {len(missing_decision)} forecastable Official players")

        decision_coverage = len(decision_ids & forecast_ids) / max(1, len(decision_ids))
        result.update({
            "health": state,
            "reasons": reasons,
            "target_gameweek": target,
            "generated_at": generated_at,
            "model_version": meta.get("model_version"),
            "age_hours": round(age, 3),
            "source_generated_before_check": generated < now,
            "freshness_rule": f"age <= {max_age_hours}h; source need not be generated inside this Apex attempt",
            "identity_universe_count": len(all_ids),
            "decision_universe_rule": "Official status != 'u'",
            "decision_universe_count": len(decision_ids),
            "forecast_player_count": len(forecast_ids),
            "decision_forecast_count": len(decision_ids & forecast_ids),
            "full_identity_coverage_ratio": round(len(all_ids & forecast_ids) / max(1, len(all_ids)), 6),
            "decision_universe_coverage_ratio": round(decision_coverage, 6),
            "coverage_ratio": round(decision_coverage, 6),
            "missing_full_universe_ids": missing_full,
            "missing_decision_universe_ids": missing_decision,
            "missing_official_ids": missing_decision,
            "excluded_unavailable_ids": sorted(unavailable_ids),
            "excluded_unavailable_classification": "NO_FORECAST_EXPECTED",
            "forecasted_unavailable_ids": forecasted_unavailable,
            "malformed_target_ids": sorted(malformed_target_ids),
            "missing_roster_codes": missing_roster_codes,
            "available_gameweeks": gws,
            "qualified_horizons": covered_horizons,
            "h1_available": 1 in covered_horizons,
            "h2_h8_available": all(h in covered_horizons for h in range(2, 9)),
            "official_public_payload_sha256": official["public_payload_sha256"],
            "source_bundle_sha256": _sha256_json({
                "meta": _sha256_bytes(raw_meta),
                "xp": _sha256_bytes(raw_xp),
                "players": _sha256_bytes(raw_players),
            }),
            "source_file_sha256": {
                "meta.json": _sha256_bytes(raw_meta),
                "xp.json": _sha256_bytes(raw_xp),
                "players.json": _sha256_bytes(raw_players),
            },
        })
    except Exception as exc:
        result.update({"health": "ERROR", "reasons": [f"{type(exc).__name__}: {exc}"]})
    _atomic_json(report, result)
    return result


def _resolve_github_commit(client: RetryHttp, repository: str, ref: str) -> dict[str, Any]:
    encoded = quote(ref, safe="")
    _, payload = _json_response(client, f"{GITHUB_API}/repos/{repository}/commits/{encoded}")
    if not isinstance(payload, dict) or not payload.get("sha"):
        raise ValueError(f"unable to resolve {repository}@{ref} to immutable commit")
    sha = str(payload["sha"])
    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise ValueError("resolved history commit is not a full SHA")
    committed_at = (((payload.get("commit") or {}).get("committer") or {}).get("date"))
    return {"sha": sha.lower(), "committed_at": committed_at}


def openfpl_readiness(
    *,
    policy_path: Path,
    lock_path: Path,
    report: Path,
    now: datetime | None = None,
    session: Any = None,
    history_ref: str = "master",
) -> dict[str, Any]:
    """Evaluate current-rules OpenFPL readiness from an immutable live history pin."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    source = _source(lock, "openfpl")
    history = _source(lock, "openfpl_current_history")
    minimum = int(policy.get("minimum_exact_rule_gameweeks", -1))
    if minimum != OPENFPL_MIN_GAMEWEEKS:
        raise ValueError(f"unexpected OpenFPL governed history floor: {minimum}")
    if (policy.get("model_contract") or {}).get("serve_authorized") is not False:
        raise ValueError("OpenFPL policy unexpectedly grants serving authority")

    payload: dict[str, Any] = {
        "schema_version": 3,
        "provider_id": "openfpl",
        "role": "EXTERNAL_DIAGNOSTIC",
        "serve_authorized": False,
        "production_influence": PRODUCTION_INFLUENCE,
        "checked_at": now.isoformat(),
        "model_export_expected_in_frozen_v2": False,
        "minimum_exact_rule_gameweeks": minimum,
        "training_label_seasons": policy.get("training_label_seasons") or [],
        "legacy_reference_weights_reused": False,
        "upstream_reference": {"repository": source["repository"], "commit": source["commit"]},
        "frozen_history_baseline": {
            "repository": history["repository"],
            "commit": history["commit"],
            "committed_at": history.get("committed_at"),
            "coverage_note": history.get("coverage_note"),
        },
        "history_ref_policy": history_ref,
        "auto_build": False,
        "auto_promotion": False,
    }
    try:
        client = RetryHttp(session or requests.Session())
        official = _official_public(client, now)
        target = int(official["target_gameweek"])
        repository = str(history["repository"])
        resolved = _resolve_github_commit(client, repository, history_ref)
        resolved_sha = str(resolved["sha"])
        history_url = f"{GITHUB_API}/repos/{repository}/contents/data/2026-27/gws?ref={resolved_sha}"
        response = client.get(history_url)
        entries = response.json()
        if not isinstance(entries, list):
            raise ValueError("OpenFPL current-history directory response must be an array")
        rows = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            match = GW_FILE_RE.match(str(entry.get("name") or ""))
            if not match:
                continue
            gw = int(match.group(1))
            if gw >= target:
                continue
            rows.append({
                "gameweek": gw,
                "name": entry.get("name"),
                "blob_sha": entry.get("sha"),
                "size": entry.get("size"),
            })
        rows.sort(key=lambda row: row["gameweek"])
        official_completed = set(int(gw) for gw in official.get("completed_gameweeks") or [])
        rows = [row for row in rows if int(row["gameweek"]) in official_completed]
        gameweeks = [int(row["gameweek"]) for row in rows]
        history_digest = _sha256_json(rows)
        ready = len(gameweeks) >= minimum
        payload.update({
            "health": "HEALTHY",
            "state": "READY_FOR_SHADOW_BUILD" if ready else "TRAINING_NOT_READY",
            "dns_reason": None if ready else "TRAINING_NOT_READY",
            "target_gameweek": target,
            "official_completed_gameweeks": sorted(official_completed),
            "completed_exact_rule_gameweeks": gameweeks,
            "exact_rule_gameweek_count": len(gameweeks),
            "history_remaining_to_floor": max(0, minimum - len(gameweeks)),
            "observed_history_commit": resolved_sha,
            "observed_history_committed_at": resolved.get("committed_at"),
            "observed_history_url": history_url,
            "observed_history_manifest_sha256": history_digest,
            "observed_history_rows": rows,
            "immutable_history_observation": True,
            "reasons": ([] if ready else [
                f"{len(gameweeks)} completed exact-rule 2026/27 gameweeks are currently available; governed minimum is {minimum}.",
                "Pinned upstream OpenFPL reference uses legacy scoring and cannot be promoted or reused as current-rules weights.",
            ]),
            "next_transition": (
                "History floor satisfied: an explicit separately governed current-rules SHADOW build may now be created and validated; no automatic build or promotion."
                if ready else
                "Continue observing completed exact-rule history from immutable resolved commits; no model export is expected until the governed floor is satisfied."
            ),
        })
    except Exception as exc:
        payload.update({
            "health": "ERROR",
            "state": "READINESS_CHECK_ERROR",
            "dns_reason": "PROVIDER_AVAILABILITY_FAILURE",
            "reasons": [f"{type(exc).__name__}: {exc}"],
            "next_transition": "Retry the isolated readiness monitor; production remains unaffected.",
        })
    _atomic_json(report, payload)
    return payload


def dastan_pin_health(
    *,
    lock_path: Path,
    report: Path,
    now: datetime | None = None,
    session: Any = None,
) -> dict[str, Any]:
    """Verify that the frozen Dastan pin remains reachable without running it."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    source = _source(lock, "dastan")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "provider_id": "dastan",
        "role": "SHADOW",
        "serve_authorized": False,
        "production_influence": PRODUCTION_INFLUENCE,
        "checked_at": now.isoformat(),
        "repository": source["repository"],
        "pinned_commit": source["commit"],
    }
    try:
        client = RetryHttp(session or requests.Session())
        _, commit = _json_response(client, f"{GITHUB_API}/repos/{source['repository']}/commits/{source['commit']}")
        observed = str(commit.get("sha") or "") if isinstance(commit, dict) else ""
        if observed.lower() != str(source["commit"]).lower():
            raise ValueError("Dastan pinned commit lookup did not resolve exact expected SHA")
        payload.update({
            "health": "HEALTHY",
            "state": "PIN_REACHABLE",
            "observed_commit": observed.lower(),
            "failure_class": None,
            "reasons": [],
        })
    except Exception as exc:
        payload.update({
            "health": "ERROR",
            "state": "PIN_PREFLIGHT_ERROR",
            "failure_class": "PROVIDER_AVAILABILITY_FAILURE",
            "reasons": [f"{type(exc).__name__}: {exc}"],
        })
    _atomic_json(report, payload)
    return payload


def _dastan_transient_failure(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in DASTAN_TRANSIENT_PATTERNS)


def _safe_failure_excerpt(text: str, limit: int = 500) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    excerpt = " | ".join(lines[-3:])
    excerpt = re.sub(r"(?i)(authorization|token|cookie|secret|password)\s*[:=]\s*\S+", r"\1=<redacted>", excerpt)
    return excerpt[-limit:]


def run_dastan_with_retry(
    *,
    runner: Path,
    expected_official_hash: str,
    lock_path: Path,
    report: Path,
    max_attempts: int = 2,
    wall_clock_seconds: float = 900.0,
    sleeper: Any = time.sleep,
    run_command: Any = subprocess.run,
) -> dict[str, Any]:
    """Run frozen Dastan with retry only for transient infrastructure failures."""
    if max_attempts < 1 or max_attempts > 3:
        raise ValueError("Dastan max_attempts must be in [1,3]")
    if wall_clock_seconds <= 0:
        raise ValueError("Dastan wall_clock_seconds must be positive")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    source = _source(lock, "dastan")
    started = time.monotonic()
    attempts: list[dict[str, Any]] = []
    final_rc = 1
    final_text = ""
    failure_class: str | None = None

    for attempt in range(1, max_attempts + 1):
        remaining = wall_clock_seconds - (time.monotonic() - started)
        if remaining <= 0:
            failure_class = "TRANSIENT_BUDGET_EXHAUSTED"
            break
        command = [sys.executable, str(runner), "--expected-official-hash", expected_official_hash]
        try:
            proc = run_command(command, capture_output=True, text=True, timeout=remaining, check=False)
            stdout = str(getattr(proc, "stdout", "") or "")
            stderr = str(getattr(proc, "stderr", "") or "")
            final_rc = int(getattr(proc, "returncode", 1))
            final_text = f"{stdout}\n{stderr}"
            if stdout:
                print(stdout, end="" if stdout.endswith("\n") else "\n")
            if stderr:
                print(stderr, file=sys.stderr, end="" if stderr.endswith("\n") else "\n")
        except subprocess.TimeoutExpired as exc:
            final_rc = 124
            stdout = str(exc.stdout or "")
            stderr = str(exc.stderr or "")
            final_text = f"{stdout}\n{stderr}\noperation timed out"
        transient = final_rc != 0 and _dastan_transient_failure(final_text)
        attempts.append({
            "attempt": attempt,
            "return_code": final_rc,
            "transient": transient,
            "output_sha256": _sha256_bytes(final_text.encode("utf-8", errors="replace")),
            "failure_excerpt": None if final_rc == 0 else _safe_failure_excerpt(final_text),
        })
        if final_rc == 0:
            failure_class = None
            break
        if not transient:
            failure_class = "PROVIDER_LOGIC_OR_INVARIANT_FAILURE"
            break
        failure_class = "TRANSIENT_INFRASTRUCTURE_FAILURE"
        if attempt < max_attempts:
            remaining = wall_clock_seconds - (time.monotonic() - started)
            if remaining <= 1.0:
                failure_class = "TRANSIENT_BUDGET_EXHAUSTED"
                break
            sleeper(min(5.0 * attempt, max(0.0, remaining - 0.5)))

    elapsed = time.monotonic() - started
    success = final_rc == 0
    payload = {
        "schema_version": 1,
        "provider_id": "dastan",
        "role": "SHADOW",
        "serve_authorized": False,
        "production_influence": PRODUCTION_INFLUENCE,
        "repository": source["repository"],
        "pinned_commit": source["commit"],
        "expected_official_hash": expected_official_hash,
        "health": "HEALTHY" if success else "ERROR",
        "state": "ACQUIRED" if success else "ACQUISITION_FAILED",
        "failure_class": failure_class,
        "attempt_count": len(attempts),
        "max_attempts": max_attempts,
        "wall_clock_budget_seconds": wall_clock_seconds,
        "elapsed_seconds": round(elapsed, 3),
        "attempts": attempts,
        "retry_policy": "recognised transient network/package-index failures only; logical/model/invariant failures are never retried",
    }
    _atomic_json(report, payload)
    return payload


def combined_health(
    *,
    config_report: Path,
    dastan_report: Path,
    pitchside_report: Path,
    openfpl_report: Path,
    output: Path,
) -> dict[str, Any]:
    payloads = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in (config_report, dastan_report, pitchside_report, openfpl_report)
    ]
    combined = {
        "schema_version": 2,
        "production_influence": PRODUCTION_INFLUENCE,
        "serving_architecture_changed": False,
        "providers": {str(p.get("provider_id") or p.get("mode")): p for p in payloads},
    }
    _atomic_json(output, combined)
    return combined


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    d = sub.add_parser("derive-runtime-config")
    d.add_argument("--source", type=Path, required=True)
    d.add_argument("--output", type=Path, required=True)
    d.add_argument("--report", type=Path, required=True)

    p = sub.add_parser("pitchside-health")
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--max-age-hours", type=float, default=18.0)

    o = sub.add_parser("openfpl-readiness")
    o.add_argument("--policy", type=Path, required=True)
    o.add_argument("--lock", type=Path, required=True)
    o.add_argument("--report", type=Path, required=True)
    o.add_argument("--history-ref", default="master")

    dp = sub.add_parser("dastan-pin-health")
    dp.add_argument("--lock", type=Path, required=True)
    dp.add_argument("--report", type=Path, required=True)

    dr = sub.add_parser("dastan-run")
    dr.add_argument("--runner", type=Path, required=True)
    dr.add_argument("--expected-official-hash", required=True)
    dr.add_argument("--lock", type=Path, required=True)
    dr.add_argument("--report", type=Path, required=True)
    dr.add_argument("--max-attempts", type=int, default=2)
    dr.add_argument("--wall-clock-seconds", type=float, default=900.0)

    c = sub.add_parser("combine")
    c.add_argument("--config-report", type=Path, required=True)
    c.add_argument("--dastan-report", type=Path, required=True)
    c.add_argument("--pitchside-report", type=Path, required=True)
    c.add_argument("--openfpl-report", type=Path, required=True)
    c.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "derive-runtime-config":
        result = derive_runtime_config(args.source, args.output, args.report)
    elif args.command == "pitchside-health":
        result = pitchside_health(report=args.report, max_age_hours=args.max_age_hours)
    elif args.command == "openfpl-readiness":
        result = openfpl_readiness(
            policy_path=args.policy,
            lock_path=args.lock,
            report=args.report,
            history_ref=args.history_ref,
        )
    elif args.command == "dastan-pin-health":
        result = dastan_pin_health(lock_path=args.lock, report=args.report)
    elif args.command == "dastan-run":
        result = run_dastan_with_retry(
            runner=args.runner,
            expected_official_hash=args.expected_official_hash,
            lock_path=args.lock,
            report=args.report,
            max_attempts=args.max_attempts,
            wall_clock_seconds=args.wall_clock_seconds,
        )
        if result["health"] != "HEALTHY":
            print(json.dumps(result, sort_keys=True))
            raise SystemExit(1)
    else:
        result = combined_health(
            config_report=args.config_report,
            dastan_report=args.dastan_report,
            pitchside_report=args.pitchside_report,
            openfpl_report=args.openfpl_report,
            output=args.output,
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
