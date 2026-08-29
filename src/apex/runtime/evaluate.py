from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import requests

from apex.governance.evaluation import score_predictions
from apex.runtime.evaluation_archive import (
    PRIVATE_EVALUATION_RELEASE_ASSETS_V1,
    load_verified_private_provider_surfaces,
)
from apex.runtime.publication import (
    PUBLIC_RELEASE_ASSETS_V1,
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


def _provider_metrics(
    provider_surfaces: dict[str, dict],
    gameweek: int,
    actual: dict[int, float],
    minutes: dict[int, float],
) -> dict:
    output = {}
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
        output[provider_id] = {
            "all": all_metrics.to_dict(),
            "starters_60plus": (
                score_predictions(starters).to_dict() if not starters.empty else None
            ),
            "coverage_rows": len(frame),
        }
    return output


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
            # Migration-only behavior for immutable releases created before the
            # privacy boundary. Never download their decision_bundle/bundle.
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
        if private_release is None:
            # Releases predating the private-evaluation archive contract cannot be
            # scored prospectively without regenerating provider rows, which is
            # forbidden. New publication code creates this private Release before
            # the public final Release, so absence is migration-only for old runs.
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
        live, actual, minutes = _live(gameweek)
        metrics = _provider_metrics(
            provider_surfaces,
            gameweek,
            actual,
            minutes,
        )
        if not metrics:
            raise RuntimeError(
                "verified private provider archive contains no scoreable H1 forecasts"
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
            "schema_version": 1,
            "season": season,
            "gameweek": gameweek,
            "run_id": run_id,
            "public_attempt_id": public_attempt["public_attempt_id"],
            "providers": metrics,
            "automatic_promotion": False,
            "note": (
                "Evaluation evidence only. Provider promotion requires explicit "
                "governed approval."
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
                "Prospective scoring only; this release never changes "
                "serving-provider authority."
            ),
        )
        published.append(evaluation_tag)
    return published
