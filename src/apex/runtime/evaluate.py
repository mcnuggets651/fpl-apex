from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path

import pandas as pd
import requests

from apex.governance.evaluation import score_predictions
from apex.runtime.releases import (
    GitHubReleaseStore,
    download_release_asset,
    verify_attested_release,
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
    snapshot_root: Path,
    gameweek: int,
    actual: dict[int, float],
    minutes: dict[int, float],
) -> dict:
    output = {}
    for path in sorted((snapshot_root / "providers").glob("*.json")):
        data = json.loads(path.read_text())
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
        output[data["provider_id"]] = {
            "all": all_metrics.to_dict(),
            "starters_60plus": (
                score_predictions(starters).to_dict() if not starters.empty else None
            ),
            "coverage_rows": len(frame),
        }
    return output


def evaluate_completed_attempts(
    store: GitHubReleaseStore,
    *,
    season: str,
    target_commitish: str,
    prefix="apex-v2",
    workdir: Path = Path("artifacts/v2/evaluation"),
) -> list[str]:
    releases = store.list_releases()
    by_tag = {release["tag_name"]: release for release in releases}
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
        decision_path = download_release_asset(
            store,
            release,
            "decision_bundle.json",
            attempt / "decision_bundle.json",
        )
        decision = json.loads(decision_path.read_text())
        gameweek = int(decision["manifest"]["target_gameweek"])
        if not finished.get(gameweek, False):
            continue
        verify_attested_release(store, release, attempt)
        bundle = attempt / "bundle.tar.gz"
        extract = attempt / "extracted"
        extract.mkdir(exist_ok=True)
        with tarfile.open(bundle, "r:gz") as archive:
            archive.extractall(extract, filter="data")
        live, actual, minutes = _live(gameweek)
        metrics = _provider_metrics(
            extract / "snapshot",
            gameweek,
            actual,
            minutes,
        )
        outcomes = {
            "schema_version": 1,
            "season": season,
            "gameweek": gameweek,
            "run_id": run_id,
            "official_live_hash": _hash(live),
            "actual_points": actual,
            "actual_minutes": minutes,
        }
        metrics_payload = {
            "schema_version": 1,
            "season": season,
            "gameweek": gameweek,
            "run_id": run_id,
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
