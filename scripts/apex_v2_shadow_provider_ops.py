#!/usr/bin/env python3
"""Operations-only reliability boundary for non-serving external diagnostics.

This controller is materialised from the control-plane SHA while the Apex V2
engine remains checked out at its frozen SHA. It never grants serving authority,
changes projections, reads manager credentials, or invokes the solver.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

EXTERNAL_DIAGNOSTIC_IDS = ("pitchside", "openfpl")
PRODUCTION_INFLUENCE = "NONE"
PITCHSIDE_BASE = "https://bjarkisigur7.github.io/fpl-ai-assistant/data"
FPL_BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_FIXTURES = "https://fantasy.premierleague.com/api/fixtures/"
OPENFPL_MIN_GAMEWEEKS = 10


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


def derive_runtime_config(source: Path, output: Path, report: Path) -> dict[str, Any]:
    """Exclude external diagnostics from frozen production qualification.

    PITCHSIDE is a periodically published external snapshot and cannot satisfy
    the frozen engine's per-attempt-generation check by construction. OpenFPL
    has no authorised 2026/27 current-rules model before its governed history
    floor. Both remain observable, but neither belongs in production
    certification for frozen V2.
    """
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
        "schema_version": 1,
        "mode": "EXTERNAL_DIAGNOSTIC_BOUNDARY",
        "production_influence": PRODUCTION_INFLUENCE,
        "frozen_config_sha256": _sha256_bytes(raw),
        "runtime_config_sha256": _sha256_bytes(output.read_bytes()),
        "removed_from_production_qualification": [str(p["id"]) for p in removed],
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
    digest = hashlib.sha256()
    digest.update(raw_bootstrap)
    digest.update(b"\0")
    digest.update(raw_fixtures)
    return {
        "target_gameweek": target,
        "elements": bootstrap.get("elements") or [],
        "public_payload_sha256": digest.hexdigest(),
    }


def pitchside_health(*, report: Path, now: datetime | None = None, session: Any = None, max_age_hours: float = 18.0) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    client = RetryHttp(session or requests.Session())
    result: dict[str, Any] = {
        "schema_version": 1,
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
        code_to_element = {
            int(e["code"]): int(e["id"])
            for e in official["elements"]
            if e.get("code") is not None and e.get("id") is not None
        }
        forecast_ids: set[int] = set()
        for raw_code, vector in forecasts.items():
            try:
                code = int(raw_code)
            except (TypeError, ValueError):
                continue
            if code not in code_to_element or not isinstance(vector, list) or idx >= len(vector):
                continue
            if vector[idx] is not None:
                forecast_ids.add(code_to_element[code])
        all_ids = {int(e["id"]) for e in official["elements"] if e.get("id") is not None}
        missing = sorted(all_ids - forecast_ids)
        state = "HEALTHY"
        reasons: list[str] = []
        if age < -0.1:
            state = "ERROR"
            reasons.append(f"source timestamp is {-age:.2f}h in the future")
        elif age > max_age_hours:
            state = "STALE"
            reasons.append(f"source age {age:.2f}h exceeds {max_age_hours:.2f}h")
        if missing:
            state = "INCOMPLETE" if state == "HEALTHY" else state
            reasons.append(f"target GW forecast missing for {len(missing)} Official players")
        result.update({
            "health": state,
            "reasons": reasons,
            "target_gameweek": target,
            "generated_at": generated_at,
            "age_hours": round(age, 3),
            "source_generated_before_check": generated < now,
            "freshness_rule": f"age <= {max_age_hours}h; source need not be generated inside this Apex attempt",
            "official_player_count": len(all_ids),
            "forecast_player_count": len(forecast_ids),
            "missing_official_ids": missing,
            "coverage_ratio": round(len(forecast_ids) / max(1, len(all_ids)), 6),
            "official_public_payload_sha256": official["public_payload_sha256"],
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


def openfpl_readiness(*, policy_path: Path, lock_path: Path, report: Path) -> dict[str, Any]:
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    source = (lock.get("sources") or {}).get("openfpl") or {}
    history = (lock.get("sources") or {}).get("openfpl_current_history") or {}
    minimum = int(policy.get("minimum_exact_rule_gameweeks", -1))
    if minimum != OPENFPL_MIN_GAMEWEEKS:
        raise ValueError(f"unexpected OpenFPL governed history floor: {minimum}")
    if (policy.get("model_contract") or {}).get("serve_authorized") is not False:
        raise ValueError("OpenFPL policy unexpectedly grants serving authority")
    payload = {
        "schema_version": 1,
        "provider_id": "openfpl",
        "role": "EXTERNAL_DIAGNOSTIC",
        "serve_authorized": False,
        "production_influence": PRODUCTION_INFLUENCE,
        "state": "DEFERRED_BY_GOVERNANCE",
        "model_export_expected_in_frozen_v2": False,
        "minimum_exact_rule_gameweeks": minimum,
        "training_label_seasons": policy.get("training_label_seasons") or [],
        "legacy_reference_weights_reused": False,
        "upstream_reference": {"repository": source.get("repository"), "commit": source.get("commit")},
        "pinned_current_history": {
            "repository": history.get("repository"),
            "commit": history.get("commit"),
            "committed_at": history.get("committed_at"),
            "coverage_note": history.get("coverage_note"),
        },
        "reasons": [
            "Frozen V2 has no authorised 2026/27 OpenFPL projection export.",
            "Governed policy requires 10 completed exact-rule 2026/27 gameweeks before model construction.",
            "Pinned upstream OpenFPL reference uses legacy scoring and cannot be promoted or reused as current-rules weights.",
        ],
        "next_transition": "A separately governed current-rules shadow build may be introduced only after the history floor and validation contract pass; no automatic promotion.",
    }
    _atomic_json(report, payload)
    return payload


def combined_health(*, config_report: Path, pitchside_report: Path, openfpl_report: Path, output: Path) -> dict[str, Any]:
    payloads = [json.loads(p.read_text(encoding="utf-8")) for p in (config_report, pitchside_report, openfpl_report)]
    combined = {
        "schema_version": 1,
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

    c = sub.add_parser("combine")
    c.add_argument("--config-report", type=Path, required=True)
    c.add_argument("--pitchside-report", type=Path, required=True)
    c.add_argument("--openfpl-report", type=Path, required=True)
    c.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "derive-runtime-config":
        result = derive_runtime_config(args.source, args.output, args.report)
    elif args.command == "pitchside-health":
        result = pitchside_health(report=args.report, max_age_hours=args.max_age_hours)
    elif args.command == "openfpl-readiness":
        result = openfpl_readiness(policy_path=args.policy, lock_path=args.lock, report=args.report)
    else:
        result = combined_health(config_report=args.config_report, pitchside_report=args.pitchside_report, openfpl_report=args.openfpl_report, output=args.output)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
