from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from apex.governance.tournament import (
    MIN_DECISION_SURFACE_COVERAGE,
    assess_promotion,
)
from apex.runtime.releases import (
    GitHubReleaseStore,
    download_release_asset,
    release_asset_map,
)


def _parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def canonical_evaluations(payloads: list[dict]) -> list[dict]:
    """Keep one hindsight-safe sealed evaluation per Gameweek.

    Daily production may create several immutable attempts for the same target
    Gameweek. Tournament standings must not overweight a Gameweek merely because
    Apex ran more often that week, so the latest sealed pre-deadline actionable
    attempt wins. Legacy payloads without the V2 tournament contract are ignored.
    """

    by_gameweek: dict[int, dict] = {}
    for payload in payloads:
        if int(payload.get("schema_version", 0)) < 2:
            continue
        frozen_at = _parse_time(payload.get("frozen_at"))
        valid_until = _parse_time(payload.get("valid_until"))
        if payload.get("certification_actionable") is not True:
            continue
        if valid_until != datetime.min.replace(tzinfo=timezone.utc) and frozen_at > valid_until:
            continue
        gameweek = int(payload["gameweek"])
        current = by_gameweek.get(gameweek)
        if current is None or frozen_at > _parse_time(current.get("frozen_at")):
            by_gameweek[gameweek] = payload
    return [by_gameweek[gw] for gw in sorted(by_gameweek)]


def _provider_season_metrics(payloads: list[dict]) -> dict[str, dict]:
    aggregate: dict[str, dict] = {}
    total_gameweeks = len(payloads)
    for payload in payloads:
        for provider_id, metrics in (payload.get("providers") or {}).items():
            row = aggregate.setdefault(
                provider_id,
                {
                    "gameweeks_available": 0,
                    "decision_surface_rows": 0,
                    "decision_surface_absolute_error_sum": 0.0,
                    "coverage_rows": 0,
                    "coverage_required_rows": 0,
                },
            )
            row["gameweeks_available"] += 1
            surface = metrics.get("decision_surface") or {}
            rows = int(surface.get("rows") or 0)
            mae = surface.get("mae")
            if mae is not None and rows:
                row["decision_surface_rows"] += rows
                row["decision_surface_absolute_error_sum"] += float(mae) * rows
            row["coverage_rows"] += int(
                metrics.get("decision_surface_forecast_rows") or 0
            )
            row["coverage_required_rows"] += int(
                metrics.get("decision_surface_required_rows") or 0
            )

    for row in aggregate.values():
        rows = row["decision_surface_rows"]
        required = row["coverage_required_rows"]
        row["decision_surface_mae"] = (
            row["decision_surface_absolute_error_sum"] / rows if rows else None
        )
        row["decision_surface_coverage"] = (
            row["coverage_rows"] / required if required else 0.0
        )
        row["delivery_ratio"] = (
            row["gameweeks_available"] / total_gameweeks if total_gameweeks else 0.0
        )
    return aggregate


def _pair_aggregate(
    payloads: list[dict],
    provider_a: str,
    provider_b: str,
) -> dict:
    first, second = sorted((str(provider_a), str(provider_b)))
    key = f"{first}::{second}"
    paired_rows = 0
    error_a = 0.0
    error_b = 0.0
    gameweeks = 0
    for payload in payloads:
        pair = (payload.get("all_pairwise") or {}).get(key)
        if not pair:
            continue
        rows = int(pair.get("paired_rows") or 0)
        if rows <= 0:
            continue
        gameweeks += 1
        paired_rows += rows
        if str(provider_a) == str(pair.get("provider_a")):
            error_a += float(pair.get("provider_a_absolute_error_sum") or 0.0)
            error_b += float(pair.get("provider_b_absolute_error_sum") or 0.0)
        else:
            error_a += float(pair.get("provider_b_absolute_error_sum") or 0.0)
            error_b += float(pair.get("provider_a_absolute_error_sum") or 0.0)
    return {
        "gameweeks": gameweeks,
        "paired_rows": paired_rows,
        "provider_a_mae": error_a / paired_rows if paired_rows else None,
        "provider_b_mae": error_b / paired_rows if paired_rows else None,
        "provider_a_absolute_error_sum": error_a,
        "provider_b_absolute_error_sum": error_b,
    }


def build_tournament_standings(payloads: list[dict]) -> dict:
    canonical = canonical_evaluations(payloads)
    if not canonical:
        return {
            "schema_version": 1,
            "status": "NO_CANONICAL_EVALUATIONS",
            "completed_gameweeks": [],
            "champion_provider_id": None,
            "providers": {},
            "challengers": {},
            "automatic_promotion": False,
        }

    latest = canonical[-1]
    champion = str(latest["champion_provider_id"])
    latest_gameweek = int(latest["gameweek"])
    provider_metrics = _provider_season_metrics(canonical)
    recent = canonical[-8:]
    champion_horizons = set(
        int(value)
        for value in (
            (latest.get("supported_horizons_by_provider") or {}).get(champion) or []
        )
    )

    challengers: dict[str, dict] = {}
    for provider_id, provider in sorted(provider_metrics.items()):
        if provider_id == champion:
            continue
        expanding = _pair_aggregate(canonical, champion, provider_id)
        recent_pair = _pair_aggregate(recent, champion, provider_id)
        horizons = set(
            int(value)
            for value in (
                (latest.get("supported_horizons_by_provider") or {}).get(provider_id)
                or []
            )
        )
        horizon_compatible = bool(champion_horizons) and champion_horizons.issubset(horizons)
        operationally_reliable = (
            float(provider.get("delivery_ratio") or 0.0)
            >= MIN_DECISION_SURFACE_COVERAGE
        )

        # Deliberately fail closed until a multi-horizon challenger has earned
        # enough forecast evidence to justify the extra shadow-optimiser work.
        # Forecast results can make a challenger interesting; they cannot promote
        # it without the frozen decision-quality sanity check.
        decision_quality_passed = False
        assessment = assess_promotion(
            gameweek=latest_gameweek,
            completed_gameweeks=int(expanding["gameweeks"]),
            paired_observations=int(expanding["paired_rows"]),
            coverage=float(provider.get("decision_surface_coverage") or 0.0),
            champion_expanding_mae=expanding["provider_a_mae"],
            challenger_expanding_mae=expanding["provider_b_mae"],
            champion_recent_mae=recent_pair["provider_a_mae"],
            challenger_recent_mae=recent_pair["provider_b_mae"],
            horizon_compatible=horizon_compatible,
            operationally_reliable=operationally_reliable,
            decision_quality_passed=decision_quality_passed,
        )
        challengers[provider_id] = {
            "expanding_pair": expanding,
            "recent_8gw_pair": recent_pair,
            "horizon_compatible": horizon_compatible,
            "operationally_reliable": operationally_reliable,
            "decision_quality_status": "NOT_YET_MEASURED",
            "promotion": assessment.to_dict(),
        }

    leaderboard = sorted(
        (
            {
                "provider_id": provider_id,
                **metrics,
            }
            for provider_id, metrics in provider_metrics.items()
        ),
        key=lambda row: (
            row["decision_surface_mae"] is None,
            row["decision_surface_mae"] if row["decision_surface_mae"] is not None else 1e9,
            row["provider_id"],
        ),
    )

    return {
        "schema_version": 1,
        "status": "OK",
        "latest_gameweek": latest_gameweek,
        "completed_gameweeks": [int(row["gameweek"]) for row in canonical],
        "canonical_attempts": [str(row["run_id"]) for row in canonical],
        "champion_provider_id": champion,
        "leaderboard": leaderboard,
        "providers": provider_metrics,
        "challengers": challengers,
        "automatic_promotion": False,
        "blending_allowed": False,
        "note": (
            "Derived prospective standings. Promotion remains explicit and fail-closed; "
            "the champion alone drives production."
        ),
    }


def load_evaluation_payloads(
    store: GitHubReleaseStore,
    *,
    season: str,
    prefix: str = "apex-v2",
    workdir: Path = Path("artifacts/v2/tournament/evaluations"),
) -> list[dict]:
    payloads: list[dict] = []
    for release in store.list_releases():
        tag = str(release.get("tag_name") or "")
        if not tag.startswith(f"{prefix}/evaluation/{season}/") or release.get("draft"):
            continue
        if not bool(release.get("immutable", False)):
            raise RuntimeError(f"tournament evaluation release is not immutable: {tag}")
        assets = release_asset_map(release)
        if set(assets) != {"metrics.json"}:
            raise RuntimeError(f"tournament evaluation asset set mismatch: {tag}")
        run_id = tag.split(f"{prefix}/evaluation/{season}/", 1)[1]
        path = download_release_asset(
            store,
            release,
            "metrics.json",
            Path(workdir) / run_id / "metrics.json",
        )
        payloads.append(json.loads(path.read_text(encoding="utf-8")))
    return payloads


def write_tournament_standings(
    store: GitHubReleaseStore,
    *,
    season: str,
    output: Path,
    prefix: str = "apex-v2",
) -> dict:
    payload = build_tournament_standings(
        load_evaluation_payloads(store, season=season, prefix=prefix)
    )
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return payload
