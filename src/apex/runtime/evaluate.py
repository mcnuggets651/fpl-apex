from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import requests

from apex.governance.evaluation import score_predictions
from apex.governance.tournament import (
    DECISION_SURFACE_METHOD,
    DISAGREEMENT_ABSOLUTE_XP,
    DISAGREEMENT_RELATIVE,
    MIN_COMPLETED_GAMEWEEKS,
    MIN_DECISION_SURFACE_COVERAGE,
    MIN_PAIRED_OBSERVATIONS,
    MIN_RELATIVE_MAE_IMPROVEMENT,
    REVIEW_GAMEWEEKS,
    build_model_neutral_decision_surface,
    disagreement_material,
    independent_challenger_consensus,
    paired_error_summaries,
)
from apex.runtime.evaluation_archive import (
    PRIVATE_EVALUATION_RELEASE_ASSETS_V1,
    load_verified_private_provider_surfaces,
)
from apex.runtime.publication import (
    PRIVATE_RELEASE_ASSETS_V1,
    PUBLIC_RELEASE_ASSETS_V1,
    sha256_file,
    verify_public_attestation,
)
from apex.runtime.releases import (
    GitHubReleaseStore,
    download_release_asset,
    release_asset_map,
)

BASE = "https://fantasy.premierleague.com/api"


def _hash(payload) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _official_finished_events(http=None):
    http = http or requests.Session()
    response = http.get(f"{BASE}/bootstrap-static/", timeout=30)
    response.raise_for_status()
    bootstrap = response.json()
    return (
        {
            int(event["id"]): bool(event.get("finished"))
            for event in bootstrap.get("events", [])
        },
        bootstrap,
    )


def _live(gameweek, http=None):
    http = http or requests.Session()
    response = http.get(f"{BASE}/event/{gameweek}/live/", timeout=30)
    response.raise_for_status()
    payload = response.json()
    actual = {}
    minutes = {}
    for element in payload.get("elements", []):
        player_id = int(element["id"])
        stats = element.get("stats", {})
        actual[player_id] = float(stats.get("total_points", 0))
        minutes[player_id] = float(stats.get("minutes", 0))
    return payload, actual, minutes


def _provider_prediction_maps(
    provider_surfaces: dict[str, dict],
    gameweek: int,
) -> tuple[dict[str, dict[int, float]], dict[str, tuple[int, ...]]]:
    predictions: dict[str, dict[int, float]] = {}
    horizons: dict[str, tuple[int, ...]] = {}
    for path, data in sorted(provider_surfaces.items()):
        provider_id = str(data.get("provider_id") or "").strip()
        if not provider_id:
            raise RuntimeError(f"private provider surface lacks provider_id: {path}")
        if provider_id in predictions:
            raise RuntimeError(
                f"duplicate private provider_id in evaluation archive: {provider_id}"
            )
        rows: dict[int, float] = {}
        for row in data.get("rows", []):
            if (
                int(row.get("gameweek", -1)) != int(gameweek)
                or int(row.get("horizon", -1)) != 1
                or row.get("coverage_status", "FORECAST") != "FORECAST"
                or row.get("expected_points") is None
            ):
                continue
            player_id = int(row["element_id"])
            if player_id in rows:
                raise RuntimeError(
                    f"duplicate H1 forecast for provider {provider_id}, player {player_id}"
                )
            rows[player_id] = float(row["expected_points"])
        predictions[provider_id] = rows
        horizons[provider_id] = tuple(
            sorted(int(value) for value in data.get("supported_horizons") or [])
        )
    return predictions, horizons


def _provider_metrics(
    provider_surfaces: dict[str, dict],
    gameweek: int,
    actual: dict[int, float],
    minutes: dict[int, float],
    decision_surface: frozenset[int],
) -> dict:
    output = {}
    required_surface = frozenset(int(pid) for pid in decision_surface if int(pid) in actual)
    for path, data in sorted(provider_surfaces.items()):
        provider_id = str(data.get("provider_id") or "").strip()
        if not provider_id:
            raise RuntimeError(f"private provider surface lacks provider_id: {path}")
        if provider_id in output:
            raise RuntimeError(f"duplicate private provider_id in evaluation archive: {provider_id}")
        rows = []
        for row in data.get("rows", []):
            if (
                int(row.get("gameweek", -1)) != gameweek
                or int(row.get("horizon", -1)) != 1
                or row.get("coverage_status", "FORECAST") != "FORECAST"
                or row.get("expected_points") is None
            ):
                continue
            player_id = int(row["element_id"])
            if player_id in actual:
                rows.append(
                    {
                        "gameweek": gameweek,
                        "element_id": player_id,
                        "predicted_points": float(row["expected_points"]),
                        "actual_points": actual[player_id],
                        "actual_minutes": minutes.get(player_id, 0),
                    }
                )
        frame = pd.DataFrame(rows)
        if frame.empty:
            continue
        all_metrics = score_predictions(frame)
        starters = frame[frame.actual_minutes >= 60]
        surface_frame = frame[frame.element_id.isin(required_surface)]
        forecast_surface_ids = frozenset(int(value) for value in surface_frame.element_id)
        denominator = len(required_surface)
        coverage = len(forecast_surface_ids) / denominator if denominator else 0.0
        output[provider_id] = {
            "all": all_metrics.to_dict(),
            "starters_60plus": (
                score_predictions(starters).to_dict() if not starters.empty else None
            ),
            "decision_surface": (
                score_predictions(surface_frame).to_dict()
                if not surface_frame.empty
                else None
            ),
            "coverage_rows": len(frame),
            "decision_surface_forecast_rows": len(forecast_surface_ids),
            "decision_surface_required_rows": denominator,
            "decision_surface_coverage": float(coverage),
            "supported_horizons": sorted(
                int(value) for value in data.get("supported_horizons") or []
            ),
        }
    return output


def _paired_vs_champion(
    predictions: dict[str, dict[int, float]],
    *,
    champion_provider_id: str,
    decision_surface: frozenset[int],
    actual: dict[int, float],
) -> dict[str, dict]:
    champion_id = str(champion_provider_id)
    champion = predictions.get(champion_id) or {}
    required = frozenset(int(pid) for pid in decision_surface if int(pid) in actual)
    output: dict[str, dict] = {}
    for challenger_id, challenger in sorted(predictions.items()):
        if challenger_id == champion_id:
            continue
        overlap = sorted(required & champion.keys() & challenger.keys())
        champion_abs_error_sum = sum(
            abs(float(champion[pid]) - float(actual[pid])) for pid in overlap
        )
        challenger_abs_error_sum = sum(
            abs(float(challenger[pid]) - float(actual[pid])) for pid in overlap
        )
        champion_mae = champion_abs_error_sum / len(overlap) if overlap else None
        challenger_mae = challenger_abs_error_sum / len(overlap) if overlap else None
        relative_improvement = None
        if champion_mae is not None and challenger_mae is not None and champion_mae > 0:
            relative_improvement = (champion_mae - challenger_mae) / champion_mae
        denominator = len(required)
        output[challenger_id] = {
            "paired_rows": len(overlap),
            "decision_surface_required_rows": denominator,
            "champion_coverage_rows": len(required & champion.keys()),
            "challenger_coverage_rows": len(required & challenger.keys()),
            "champion_coverage": (
                len(required & champion.keys()) / denominator if denominator else 0.0
            ),
            "challenger_coverage": (
                len(required & challenger.keys()) / denominator if denominator else 0.0
            ),
            "champion_absolute_error_sum": float(champion_abs_error_sum),
            "challenger_absolute_error_sum": float(challenger_abs_error_sum),
            "champion_mae": champion_mae,
            "challenger_mae": challenger_mae,
            "relative_mae_improvement": relative_improvement,
        }
    return output


def _material_disagreement_count(
    predictions: dict[str, dict[int, float]],
    *,
    champion_provider_id: str,
    decision_surface: frozenset[int],
) -> int:
    champion_id = str(champion_provider_id)
    champion = predictions.get(champion_id) or {}
    count = 0
    for player_id in decision_surface:
        if player_id not in champion:
            continue
        forecasts = {
            provider_id: rows[player_id]
            for provider_id, rows in predictions.items()
            if player_id in rows
        }
        consensus = independent_challenger_consensus(champion_id, forecasts)
        if consensus is not None and disagreement_material(champion[player_id], consensus):
            count += 1
    return count


def _download_public_attempt(
    store: GitHubReleaseStore,
    release: dict,
    attempt: Path,
) -> dict[str, Path] | None:
    """Download only the post-privacy-boundary public contract.

    Immutable releases created before the privacy boundary used the legacy
    bundle/decision asset set. They remain historical records but are not
    eligible for the new evaluator because opening that format would
    reintroduce the private-capable publication dependency we are removing.
    """

    assets = release_asset_map(release)
    if frozenset(assets) != PUBLIC_RELEASE_ASSETS_V1:
        return None
    if not bool(release.get("immutable", False)):
        raise RuntimeError(f"release is not immutable: {release.get('tag_name')}")

    files: dict[str, Path] = {}
    public_root = Path(attempt) / "public"
    public_root.mkdir(parents=True, exist_ok=True)
    for name in sorted(PUBLIC_RELEASE_ASSETS_V1):
        files[name] = download_release_asset(
            store,
            release,
            name,
            public_root / name,
        )
    verify_public_attestation(files)
    return files


def _download_private_provider_surfaces(
    store: GitHubReleaseStore,
    release: dict,
    attempt: Path,
    *,
    public_attempt_id: str,
    public_provenance_archive: Path,
) -> dict[str, dict]:
    assets = release_asset_map(release)
    if frozenset(assets) != PRIVATE_EVALUATION_RELEASE_ASSETS_V1:
        raise RuntimeError(
            f"private evaluation release asset set mismatch: {release.get('tag_name')}"
        )
    if not bool(release.get("immutable", False)):
        raise RuntimeError(
            f"private evaluation release is not immutable: {release.get('tag_name')}"
        )

    private_root = Path(attempt) / "private-evaluation"
    private_root.mkdir(parents=True, exist_ok=True)
    files = {
        name: download_release_asset(
            store,
            release,
            name,
            private_root / name,
        )
        for name in sorted(PRIVATE_EVALUATION_RELEASE_ASSETS_V1)
    }
    return load_verified_private_provider_surfaces(
        public_provenance_archive,
        files,
        public_attempt_id=public_attempt_id,
    )


def _download_private_manager_attempt(
    store: GitHubReleaseStore,
    release: dict,
    attempt: Path,
    *,
    public_attempt_id: str,
) -> dict:
    assets = release_asset_map(release)
    if frozenset(assets) != PRIVATE_RELEASE_ASSETS_V1:
        raise RuntimeError(
            f"private manager release asset set mismatch: {release.get('tag_name')}"
        )
    if not bool(release.get("immutable", False)):
        raise RuntimeError(
            f"private manager release is not immutable: {release.get('tag_name')}"
        )

    private_root = Path(attempt) / "private-manager"
    private_root.mkdir(parents=True, exist_ok=True)
    files = {
        name: download_release_asset(
            store,
            release,
            name,
            private_root / name,
        )
        for name in sorted(PRIVATE_RELEASE_ASSETS_V1)
    }
    attestation = json.loads(files["private_attestation.json"].read_text(encoding="utf-8"))
    if attestation.get("scope") != "PRIVATE_MANAGER":
        raise RuntimeError("private manager attestation scope mismatch")
    if str(attestation.get("public_attempt_id") or "") != str(public_attempt_id):
        raise RuntimeError("private manager release belongs to a different public attempt")
    expected_assets = {
        "private_manager_attempt.json": sha256_file(files["private_manager_attempt.json"])
    }
    if attestation.get("assets") != expected_assets:
        raise RuntimeError("private manager attestation asset hashes do not match")

    payload = json.loads(files["private_manager_attempt.json"].read_text(encoding="utf-8"))
    if str(payload.get("public_attempt_id") or "") != str(public_attempt_id):
        raise RuntimeError("private manager attempt public identity mismatch")
    if not isinstance(payload.get("team_state"), dict):
        raise RuntimeError("private manager attempt lacks TeamState")
    return payload


def evaluate_completed_attempts(
    store: GitHubReleaseStore,
    *,
    private_store: GitHubReleaseStore | None = None,
    season: str,
    target_commitish: str,
    prefix="apex-v2",
    workdir: Path = Path("artifacts/v2/evaluation"),
) -> list[str]:
    releases = store.list_releases()
    by_tag = {release["tag_name"]: release for release in releases}
    private_by_tag = (
        {release["tag_name"]: release for release in private_store.list_releases()}
        if private_store is not None
        else {}
    )
    finished, _ = _official_finished_events()
    published = []
    finals = [
        release
        for release in releases
        if str(release.get("tag_name", "")).startswith(
            f"{prefix}/final/{season}/"
        )
        and not release.get("draft")
    ]
    for release in finals:
        run_id = release["tag_name"].split(f"{prefix}/final/{season}/", 1)[1]
        evaluation_tag = f"{prefix}/evaluation/{season}/{run_id}"
        if evaluation_tag in by_tag:
            continue
        attempt = Path(workdir) / run_id
        attempt.mkdir(parents=True, exist_ok=True)

        files = _download_public_attempt(store, release, attempt)
        if files is None:
            continue

        public_attempt = json.loads(
            files["public_attempt.json"].read_text(encoding="utf-8")
        )
        if public_attempt.get("season") != season:
            raise RuntimeError("public attempt season does not match release namespace")
        if public_attempt.get("run_id") != run_id:
            raise RuntimeError("public attempt run_id does not match release namespace")
        gameweek = int(public_attempt["target_gameweek"])
        if not finished.get(gameweek, False):
            continue

        private_tag = f"{prefix}/private-evaluation/{season}/{run_id}"
        private_release = private_by_tag.get(private_tag)
        manager_tag = f"{prefix}/private/{season}/{run_id}"
        manager_release = private_by_tag.get(manager_tag)
        if private_release is None or manager_release is None:
            # Migration-only: old releases lacking either private pre-deadline
            # surface cannot be upgraded retrospectively without hindsight.
            continue
        if private_store is None:
            raise RuntimeError("private evaluation release exists but no private store is configured")

        provider_surfaces = _download_private_provider_surfaces(
            private_store,
            private_release,
            attempt,
            public_attempt_id=str(public_attempt["public_attempt_id"]),
            public_provenance_archive=files["provider_forecasts.tar.gz"],
        )
        manager_attempt = _download_private_manager_attempt(
            private_store,
            manager_release,
            attempt,
            public_attempt_id=str(public_attempt["public_attempt_id"]),
        )
        decision_surface = build_model_neutral_decision_surface(
            manager_attempt,
            provider_surfaces,
            gameweek=gameweek,
        )
        if not decision_surface:
            raise RuntimeError("model-neutral decision surface is empty")

        live, actual, minutes = _live(gameweek)
        metrics = _provider_metrics(
            provider_surfaces,
            gameweek,
            actual,
            minutes,
            decision_surface,
        )
        if not metrics:
            raise RuntimeError(
                "verified private provider archive contains no scoreable H1 forecasts"
            )

        predictions, supported_horizons = _provider_prediction_maps(
            provider_surfaces,
            gameweek,
        )
        serving_h1 = public_attempt.get("serving_provider_by_horizon") or {}
        champion_provider_id = str(
            serving_h1.get("1") or serving_h1.get(1) or ""
        ).strip()
        if not champion_provider_id or champion_provider_id not in predictions:
            raise RuntimeError("public attempt does not identify a scoreable H1 champion")
        paired = _paired_vs_champion(
            predictions,
            champion_provider_id=champion_provider_id,
            decision_surface=decision_surface,
            actual=actual,
        )
        all_pairwise = paired_error_summaries(
            predictions,
            decision_surface=decision_surface,
            actual=actual,
        )
        disagreement_count = _material_disagreement_count(
            predictions,
            champion_provider_id=champion_provider_id,
            decision_surface=decision_surface,
        )

        outcomes = {
            "schema_version": 1,
            "season": season,
            "gameweek": gameweek,
            "run_id": run_id,
            "public_attempt_id": public_attempt["public_attempt_id"],
            "official_live_hash": _hash(live),
            "actual_points": actual,
            "actual_minutes": minutes,
        }
        metrics_payload = {
            "schema_version": 2,
            "season": season,
            "gameweek": gameweek,
            "run_id": run_id,
            "public_attempt_id": public_attempt["public_attempt_id"],
            "frozen_at": public_attempt.get("frozen_at"),
            "champion_provider_id": champion_provider_id,
            "providers": metrics,
            "paired_vs_champion": paired,
            "all_pairwise": all_pairwise,
            "decision_surface": {
                "method": DECISION_SURFACE_METHOD,
                "player_count": len(decision_surface),
                "player_ids_published": False,
                "shadow_optimizer_candidates_included": False,
            },
            "material_disagreement_count": int(disagreement_count),
            "supported_horizons_by_provider": {
                provider_id: list(values)
                for provider_id, values in sorted(supported_horizons.items())
            },
            "tournament_policy": {
                "review_gameweeks": list(REVIEW_GAMEWEEKS),
                "min_completed_gameweeks": MIN_COMPLETED_GAMEWEEKS,
                "min_paired_observations": MIN_PAIRED_OBSERVATIONS,
                "min_decision_surface_coverage": MIN_DECISION_SURFACE_COVERAGE,
                "min_relative_mae_improvement": MIN_RELATIVE_MAE_IMPROVEMENT,
                "disagreement_absolute_xp": DISAGREEMENT_ABSOLUTE_XP,
                "disagreement_relative": DISAGREEMENT_RELATIVE,
                "blending_allowed": False,
                "automatic_promotion": False,
            },
            "automatic_promotion": False,
            "note": (
                "Prospective champion-challenger evidence only. The champion alone "
                "drives production. Promotion requires the frozen review policy and "
                "an explicit governed change; challenger forecasts are never blended."
            ),
        }
        outcomes_path = attempt / "outcomes.json"
        metrics_path = attempt / "metrics.json"
        outcomes_path.write_text(
            json.dumps(outcomes, indent=2, sort_keys=True) + "\n"
        )
        metrics_path.write_text(
            json.dumps(
                metrics_payload,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        )
        store.create_once(
            f"{prefix}/outcome/{season}/{run_id}",
            {"outcomes.json": outcomes_path},
            target_commitish=target_commitish,
            name=f"Apex V2 outcome {season} GW{gameweek} {run_id}",
        )
        store.create_once(
            evaluation_tag,
            {"metrics.json": metrics_path},
            target_commitish=target_commitish,
            name=f"Apex V2 evaluation {season} GW{gameweek} {run_id}",
            body=(
                "Prospective champion-challenger scoring only; this release never "
                "changes serving-provider authority."
            ),
        )
        published.append(evaluation_tag)
    return published
