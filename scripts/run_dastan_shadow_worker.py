#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from apex.forecast.dastan_live import (
    add_live_snapshot_features,
    aggregate_prediction_rows,
    assert_feature_invariance,
    build_target_player_rows,
    build_target_team_rows,
    mapping_by_fpl_code,
    target_gameweek,
)
from apex.sources.official import fetch_official_snapshot

ROOT = Path(__file__).resolve().parents[1]
SCORING_RULES_VERSION = "fpl-2026-27-v1"
SEASONS = ["2025-26", "2026-27"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def patch_dastan_checkout(
    dastan_root: Path,
    *,
    history_commit: str,
    identity_preflight: dict[str, Any],
) -> dict[str, Any]:
    """Apply an attempt-local source/mapping overlay after release verification.

    The public Dastan checkout is disposable. These edits are never committed back to
    Dastan and are fingerprinted in the worker manifest.
    """
    source_pins_path = dastan_root / "data/source_pins.json"
    clubs_path = dastan_root / "data/mappings/current_fpl_understat_clubs.csv"
    original_source_hash = sha256_file(source_pins_path)
    original_clubs_hash = sha256_file(clubs_path)

    pins = json.loads(source_pins_path.read_text(encoding="utf-8"))
    previous_history_commit = str(pins["vaastav"]["commit"])
    pins["vaastav"]["commit"] = str(history_commit)
    pins["note"] = (
        "Attempt-local Apex Dastan shadow reconstruction pin. "
        "The immutable Dastan release remains unchanged."
    )
    source_pins_path.write_text(
        json.dumps(pins, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    clubs = pd.read_csv(clubs_path)
    overlays = identity_preflight.get("club_overlay", [])
    for overlay in overlays:
        club_name = str(overlay["club_name"])
        mask = clubs["club_name"].astype(str).eq(club_name)
        if int(mask.sum()) != 1:
            raise RuntimeError(
                f"Dastan club mapping expected exactly one {club_name!r} row, got {int(mask.sum())}"
            )
        clubs.loc[mask, "understat_name"] = str(overlay["understat_name"])
        clubs.loc[mask, "understat_team_id"] = int(overlay["understat_team_id"])
        clubs.loc[mask, "mapping_status"] = "mapped"
    if clubs[["understat_name", "understat_team_id"]].isna().any().any():
        missing = clubs.loc[
            clubs[["understat_name", "understat_team_id"]].isna().any(axis=1),
            "club_name",
        ].astype(str).tolist()
        raise RuntimeError(f"attempt-local Dastan club map still unresolved: {missing}")
    clubs.to_csv(clubs_path, index=False, lineterminator="\n")

    return {
        "dastan_release_source_pins_sha256": original_source_hash,
        "dastan_release_clubs_sha256": original_clubs_hash,
        "previous_vaastav_commit": previous_history_commit,
        "attempt_history_commit": history_commit,
        "attempt_source_pins_sha256": sha256_file(source_pins_path),
        "attempt_clubs_sha256": sha256_file(clubs_path),
    }


def _target_frame(
    completed_players: pd.DataFrame,
    completed_teams: pd.DataFrame,
    *,
    bootstrap: dict[str, Any],
    fixtures: list[dict[str, Any]],
    gameweek: int,
    understat_by_code: dict[int, int],
    understat_name_by_fpl_team: dict[str, str],
    outcome_marker: float,
    sentinel_base: float,
    build_feature_frame,
) -> pd.DataFrame:
    target_players = build_target_player_rows(
        bootstrap,
        fixtures,
        gameweek=gameweek,
        understat_by_code=understat_by_code,
        understat_name_by_fpl_team=understat_name_by_fpl_team,
        outcome_marker=outcome_marker,
    )
    target_teams = build_target_team_rows(
        bootstrap,
        fixtures,
        gameweek=gameweek,
        understat_name_by_fpl_team=understat_name_by_fpl_team,
        sentinel_base=sentinel_base,
    )
    player_matches = pd.concat(
        [completed_players, target_players], ignore_index=True, sort=False
    )
    team_matches = pd.concat(
        [completed_teams, target_teams], ignore_index=True, sort=False
    )
    frame = build_feature_frame(player_matches, team_matches)
    frame = add_live_snapshot_features(frame, bootstrap, gameweek=gameweek)
    target = frame[
        frame["season"].eq("2026-27") & frame["gameweek"].eq(int(gameweek))
    ].copy()
    if target.empty:
        raise RuntimeError("Dastan live feature build produced no target rows")
    return target.sort_values(["fpl_code", "fixture"], kind="mergesort").reset_index(
        drop=True
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate leakage-safe Dastan H1 shadow xP")
    parser.add_argument("--dastan-root", required=True, type=Path)
    parser.add_argument("--identity-preflight", required=True, type=Path)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()

    dastan_root = args.dastan_root.resolve()
    if not (dastan_root / "models/artifact_manifest.json").is_file():
        raise SystemExit(f"not a verified Dastan checkout: {dastan_root}")
    if not args.identity_preflight.is_file():
        raise SystemExit(f"identity preflight missing: {args.identity_preflight}")

    lock = json.loads((ROOT / "upstreams.lock.json").read_text(encoding="utf-8"))["sources"]
    dastan_source = lock["dastan"]
    history_source = lock["dastan_live_history"]
    identity = json.loads(args.identity_preflight.read_text(encoding="utf-8"))

    official, raw = fetch_official_snapshot(season="2026-2027", timeout=30.0)
    bootstrap = raw["bootstrap"]
    fixtures = raw["fixtures"]
    gameweek = target_gameweek(bootstrap)
    expected_deadline = official.deadlines.get(gameweek)
    if not expected_deadline:
        raise RuntimeError(f"Official FPL target GW{gameweek} missing deadline")

    overlay_manifest = patch_dastan_checkout(
        dastan_root,
        history_commit=str(history_source["commit"]),
        identity_preflight=identity,
    )

    # Import only after the attempt-local source and club overlays are frozen on disk.
    sys.path.insert(0, str(dastan_root))
    from dastan import predictor  # type: ignore
    from dastan.rebuild import features as dastan_features  # type: ignore
    from dastan.rebuild.sources import (  # type: ignore
        build_canonical_matches,
        download_sources,
    )

    clubs_path = dastan_root / "data/mappings/current_fpl_understat_clubs.csv"
    current_mapping_path = dastan_root / "data/mappings/fpl_understat_current.csv"
    club_rows = csv_rows(clubs_path)
    understat_name_by_fpl_team = {
        str(row["club_name"]): str(row["understat_name"])
        for row in club_rows
        if row.get("understat_name")
    }
    for fpl_name, understat_name in understat_name_by_fpl_team.items():
        if fpl_name != understat_name:
            dastan_features.FPL_TO_UNDERSTAT[fpl_name] = understat_name
    understat_by_code = mapping_by_fpl_code(csv_rows(current_mapping_path))

    args.raw_dir.mkdir(parents=True, exist_ok=True)
    download_manifest_path = download_sources(
        args.raw_dir,
        SEASONS,
        workers=12,
        force=False,
        allow_missing_understat=False,
    )
    completed_players, completed_teams, _ = build_canonical_matches(
        args.raw_dir, SEASONS
    )

    first = _target_frame(
        completed_players,
        completed_teams,
        bootstrap=bootstrap,
        fixtures=fixtures,
        gameweek=gameweek,
        understat_by_code=understat_by_code,
        understat_name_by_fpl_team=understat_name_by_fpl_team,
        outcome_marker=0.0,
        sentinel_base=100_000.0,
        build_feature_frame=dastan_features.build_feature_frame,
    )
    second = _target_frame(
        completed_players,
        completed_teams,
        bootstrap=bootstrap,
        fixtures=fixtures,
        gameweek=gameweek,
        understat_by_code=understat_by_code,
        understat_name_by_fpl_team=understat_name_by_fpl_team,
        outcome_marker=9_999.0,
        sentinel_base=900_000.0,
        build_feature_frame=dastan_features.build_feature_frame,
    )

    model = predictor.Dastan(dastan_root / "models")
    assert_feature_invariance(first, second, model.features)
    predicted = model.predict_frame(first, with_parts=True)
    rows = aggregate_prediction_rows(
        predicted,
        bootstrap,
        fixtures,
        gameweek=gameweek,
    )

    generated_at = datetime.now(timezone.utc).isoformat()
    player_by_id = {int(row["id"]): row for row in bootstrap["elements"]}
    for row in rows:
        player = player_by_id[int(row["player_id"])]
        row.update(
            {
                "fpl_code": int(player["code"]),
                "web_name": str(player.get("web_name") or row["player_id"]),
                "generated_at": generated_at,
                "provider_version": str(dastan_source["commit"]),
                "source_snapshot": official.source_hash,
                "scoring_rules_version": SCORING_RULES_VERSION,
            }
        )
    output = pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output, index=False, lineterminator="\n")

    forecast_count = int(output["coverage_status"].eq("FORECAST").sum())
    no_forecast_count = int(output["coverage_status"].eq("NO_FORECAST").sum())
    manifest = {
        "schema_version": 1,
        "generated_at": generated_at,
        "target_gameweek": gameweek,
        "target_deadline": expected_deadline,
        "official_source_hash": official.source_hash,
        "official_raw_hashes": raw["raw_hashes"],
        "official_players": len(bootstrap["elements"]),
        "dastan_commit": str(dastan_source["commit"]),
        "history_repository": str(history_source["repository"]),
        "history_commit": str(history_source["commit"]),
        "scoring_rules_version": SCORING_RULES_VERSION,
        "seasons_rebuilt": SEASONS,
        "identity_preflight_sha256": sha256_file(args.identity_preflight),
        "download_manifest_sha256": sha256_file(Path(download_manifest_path)),
        "output_sha256": sha256_file(args.output),
        "placeholder_invariance": True,
        "forecast_rows": forecast_count,
        "no_forecast_rows": no_forecast_count,
        "serve_authorized": False,
        "predictive_status": "INSUFFICIENT_HISTORY",
        "attempt_overlay": overlay_manifest,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
