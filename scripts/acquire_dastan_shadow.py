from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import time
import venv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from apex.forecast.adapters.dastan import load_dastan
from apex.forecast.qualification import qualify_surface
from apex.runtime.config import CURRENT_SCORING_RULES_VERSION
from apex.sources.official import fetch_official_snapshot


def _run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
) -> None:
    subprocess.run(
        command,
        check=True,
        env=env,
        timeout=timeout_seconds,
    )


def _remaining_seconds(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Dastan shadow acquisition exceeded its total time budget")
    return remaining


def _python_in_venv(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _distribution(values: Iterable[float | None]) -> dict[str, float | int | None]:
    clean = sorted(
        float(value)
        for value in values
        if value is not None and math.isfinite(float(value))
    )
    if not clean:
        return {
            "count": 0,
            "min": None,
            "p50": None,
            "p95": None,
            "max": None,
            "mean": None,
        }

    def percentile(q: float) -> float:
        if len(clean) == 1:
            return clean[0]
        position = (len(clean) - 1) * q
        lower = int(math.floor(position))
        upper = int(math.ceil(position))
        if lower == upper:
            return clean[lower]
        weight = position - lower
        return clean[lower] * (1.0 - weight) + clean[upper] * weight

    return {
        "count": len(clean),
        "min": clean[0],
        "p50": percentile(0.50),
        "p95": percentile(0.95),
        "max": clean[-1],
        "mean": sum(clean) / len(clean),
    }


def _write_qualification_report(
    *,
    forecast_path: Path,
    manifest_path: Path,
    output_path: Path,
    expected_official_hash: str,
    max_age_hours: float,
) -> dict:
    official, _ = fetch_official_snapshot(season="2026-2027")
    if official.source_hash != expected_official_hash:
        raise RuntimeError(
            "Official FPL authority state changed during Dastan shadow acquisition: "
            f"expected {expected_official_hash}, got {official.source_hash}"
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("official_source_hash") != expected_official_hash:
        raise RuntimeError(
            "Dastan manifest source snapshot mismatch: "
            f"{manifest.get('official_source_hash')} != {expected_official_hash}"
        )
    if manifest.get("scoring_rules_version") != CURRENT_SCORING_RULES_VERSION:
        raise RuntimeError(
            "Dastan manifest scoring rules mismatch: "
            f"{manifest.get('scoring_rules_version')} != "
            f"{CURRENT_SCORING_RULES_VERSION}"
        )
    if bool(manifest.get("serve_authorized")):
        raise RuntimeError("Dastan shadow manifest unexpectedly grants serving authority")
    if manifest.get("predictive_status") != "INSUFFICIENT_HISTORY":
        raise RuntimeError(
            "Dastan shadow predictive status must remain INSUFFICIENT_HISTORY"
        )
    if not bool(manifest.get("placeholder_invariance")):
        raise RuntimeError("Dastan future-placeholder invariance proof did not pass")

    target_gameweek = int(manifest["target_gameweek"])
    surface = load_dastan(
        forecast_path,
        official=official,
        target_gameweek=target_gameweek,
    )
    qualification = qualify_surface(
        surface,
        official,
        decision_universe=official.decision_universe(),
        requested_horizons=(1,),
        max_age_hours=max_age_hours,
        required_scoring_rules_version=CURRENT_SCORING_RULES_VERSION,
        now=datetime.now(timezone.utc),
    )

    h1 = tuple(row for row in surface.rows if row.horizon == 1)
    forecast_rows = tuple(
        row for row in h1 if row.coverage_status.value == "FORECAST"
    )
    covered_ids = {row.element_id for row in forecast_rows}
    official_ids = set(official.player_ids)
    missing_official_ids = sorted(official_ids - covered_ids)
    extra_ids = sorted(covered_ids - official_ids)

    probability_excesses = [
        float(row.p_60) - float(row.p_appearance)
        for row in forecast_rows
        if row.p_60 is not None
        and row.p_appearance is not None
        and float(row.p_60) > float(row.p_appearance)
    ]
    material_probability_order_violations = [
        excess for excess in probability_excesses if excess > 1e-6
    ]
    probability_range_violations = 0
    nonfinite_rows = 0
    minute_range_violations = 0
    for row in forecast_rows:
        numeric = [
            row.expected_points,
            row.expected_minutes,
            row.p_appearance,
            row.p_start,
            row.p_60,
        ]
        if any(
            value is not None and not math.isfinite(float(value))
            for value in numeric
        ):
            nonfinite_rows += 1
        for value in (row.p_appearance, row.p_start, row.p_60):
            if value is not None and not (-1e-9 <= float(value) <= 1.0 + 1e-9):
                probability_range_violations += 1
        if row.expected_minutes is not None:
            maximum = 90.0 * max(1, int(row.n_fixtures)) + 1e-6
            if not (-1e-6 <= float(row.expected_minutes) <= maximum):
                minute_range_violations += 1

    report = {
        "schema_version": 1,
        "provider_id": "dastan",
        "provider_version": surface.provider_version,
        "generated_at": surface.generated_at,
        "target_gameweek": target_gameweek,
        "source_snapshot": surface.source_snapshot,
        "scoring_rules_version": surface.scoring_rules_version,
        "operational_qualification": qualification.operational.value,
        "health": qualification.health.value,
        "qualified_horizons": list(qualification.qualified_horizons),
        "qualification_reasons": list(qualification.reasons),
        "predictive_status": "INSUFFICIENT_HISTORY",
        "serve_authorized": False,
        "official_players": len(official_ids),
        "h1_rows": len(h1),
        "forecast_rows": len(forecast_rows),
        "no_forecast_rows": len(h1) - len(forecast_rows),
        "official_forecast_coverage": (
            len(official_ids & covered_ids) / len(official_ids)
            if official_ids
            else 0.0
        ),
        "missing_official_ids": missing_official_ids,
        "extra_official_ids": extra_ids,
        "xp": _distribution(row.expected_points for row in forecast_rows),
        "expected_minutes": _distribution(
            row.expected_minutes for row in forecast_rows
        ),
        "p_any": _distribution(row.p_appearance for row in forecast_rows),
        "p60": _distribution(row.p_60 for row in forecast_rows),
        "nonfinite_rows": nonfinite_rows,
        "probability_range_violations": probability_range_violations,
        "p60_gt_p_any_rows": len(probability_excesses),
        "max_p60_gt_p_any_excess": max(probability_excesses, default=0.0),
        "material_probability_order_violations": len(
            material_probability_order_violations
        ),
        "minute_range_violations": minute_range_violations,
        "placeholder_invariance": bool(manifest["placeholder_invariance"]),
        "history_repository": manifest.get("history_repository"),
        "history_commit": manifest.get("history_commit"),
        "download_manifest_sha256": manifest.get("download_manifest_sha256"),
        "output_sha256": manifest.get("output_sha256"),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if nonfinite_rows:
        raise RuntimeError(
            f"Dastan H1 contains {nonfinite_rows} non-finite forecast rows"
        )
    if probability_range_violations:
        raise RuntimeError(
            f"Dastan H1 contains {probability_range_violations} "
            "out-of-range probabilities"
        )
    if material_probability_order_violations:
        raise RuntimeError(
            "Dastan H1 contains material p60 > p_any probability incoherence"
        )
    if minute_range_violations:
        raise RuntimeError(
            f"Dastan H1 contains {minute_range_violations} "
            "impossible expected-minute rows"
        )
    if missing_official_ids or extra_ids:
        raise RuntimeError(
            "Dastan H1 does not have one FORECAST for every current Official FPL player"
        )
    return report


def acquire(args: argparse.Namespace) -> dict:
    root = Path(args.repo_root).resolve()
    worker = root / args.worker_dir
    venv_dir = root / args.venv_dir
    artifacts = root / "artifacts/v2/challengers"
    provider_dir = root / "acquisition/providers"
    raw_dir = root / ".dastan-raw"
    forecast_path = provider_dir / "dastan.csv"
    preflight_path = artifacts / "dastan_identity_preflight.json"
    manifest_path = artifacts / "dastan_shadow_manifest.json"
    qualification_path = artifacts / "dastan_shadow_qualification.json"
    deadline = time.monotonic() + float(args.total_timeout_seconds)

    def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
        _run(
            command,
            env=env,
            timeout_seconds=_remaining_seconds(deadline),
        )

    pins = json.loads(
        (root / "upstreams.lock.json").read_text(encoding="utf-8")
    )["sources"]["dastan"]
    repository = str(pins["repository"])
    commit = str(pins["commit"])

    for path in (worker, venv_dir):
        if path.exists():
            shutil.rmtree(path)
    artifacts.mkdir(parents=True, exist_ok=True)
    provider_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    forecast_path.unlink(missing_ok=True)
    qualification_path.unlink(missing_ok=True)

    run(
        [
            "git",
            "clone",
            "--filter=blob:none",
            f"https://github.com/{repository}.git",
            str(worker),
        ]
    )
    run(["git", "-C", str(worker), "checkout", "--detach", commit])

    _remaining_seconds(deadline)
    venv.EnvBuilder(with_pip=True, clear=True).create(venv_dir)
    provider_python = _python_in_venv(venv_dir)
    run([str(provider_python), "-m", "pip", "install", "-e", str(root)])
    run(
        [
            str(provider_python),
            "-m",
            "pip",
            "install",
            "-r",
            str(worker / "requirements-data.txt"),
        ]
    )

    provider_env = os.environ.copy()
    provider_env["PYTHONPATH"] = str(worker)
    run([str(provider_python), "-m", "dastan.artifacts"], env=provider_env)
    run(
        [
            str(provider_python),
            str(root / "scripts/dastan_identity_preflight.py"),
            "--mapping",
            str(worker / "data/mappings/fpl_understat_current.csv"),
            "--output",
            str(preflight_path),
        ],
        env=provider_env,
    )
    run(
        [
            str(provider_python),
            str(root / "scripts/run_dastan_shadow_worker.py"),
            "--dastan-root",
            str(worker),
            "--identity-preflight",
            str(preflight_path),
            "--raw-dir",
            str(raw_dir),
            "--output",
            str(forecast_path),
            "--manifest",
            str(manifest_path),
        ],
        env=provider_env,
    )

    _remaining_seconds(deadline)
    report = _write_qualification_report(
        forecast_path=forecast_path,
        manifest_path=manifest_path,
        output_path=qualification_path,
        expected_official_hash=args.expected_official_hash,
        max_age_hours=float(args.max_age_hours),
    )
    print(json.dumps(report, sort_keys=True))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Acquire and qualify the pinned Dastan H1 forecast as a "
            "non-serving Apex V2 shadow."
        )
    )
    parser.add_argument("--expected-official-hash", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--worker-dir", default="workers/dastan")
    parser.add_argument("--venv-dir", default=".provider-envs/dastan")
    parser.add_argument("--max-age-hours", type=float, default=18.0)
    parser.add_argument(
        "--total-timeout-seconds",
        type=float,
        default=900.0,
        help=(
            "Hard wall-clock budget for the optional non-serving shadow. "
            "Expiry fails Dastan without blocking the serving incumbent."
        ),
    )
    args = parser.parse_args()
    if args.total_timeout_seconds <= 0:
        parser.error("--total-timeout-seconds must be positive")
    acquire(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
