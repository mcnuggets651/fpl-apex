#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from apex.forecast.dastan_live import (
    add_live_snapshot_features,
    aggregate_prediction_rows,
    build_target_player_rows,
    build_target_team_rows,
    mapping_by_fpl_code,
    target_gameweek,
)
from apex.sources.official import fetch_official_snapshot

SEASONS = ["2025-26", "2026-27"]
SCORING_RULES_VERSION = "fpl-2026-27-v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_mapping(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _patch_dastan_identity(club_overlay: list[dict]) -> dict[str, str]:
    from dastan import mappings
    from dastan.rebuild import features

    base_loader = mappings.load_operational_clubs
    overlay_by_club = {str(row["club_name"]): row for row in club_overlay}

    def load_operational_clubs_with_overlay():
        frame = base_loader().copy()
        for club_name, row in overlay_by_club.items():
            mask = frame["club_name"].astype(str).eq(club_name)
            if int(mask.sum()) != 1:
                raise RuntimeError(
                    f"Dastan operational club overlay expected one {club_name!r} row, "
                    f"got {int(mask.sum())}"
                )
            frame.loc[mask, "understat_name"] = str(row["understat_name"])
            frame.loc[mask, "understat_team_id"] = int(row["understat_team_id"])
            frame.loc[mask, "mapping_status"] = "mapped"
        return frame

    mappings.load_operational_clubs = load_operational_clubs_with_overlay
    for club_name, row in overlay_by_club.items():
        features.FPL_TO_UNDERSTAT[club_name] = str(row["understat_name"])
    return {club: str(row["understat_name"]) for club, row in overlay_by_club.items()}


def _patch_vaastav_pin(commit: str) -> None:
    from dastan.rebuild import sources

    sources.VAASTAV_COMMIT = str(commit)
    sources.VAASTAV_RAW = (
        "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/"
        f"{commit}/"
    )
    sources.VAASTAV_TREE = (
        "https://api.github.com/repos/vaastav/Fantasy-Premier-League/git/trees/"
        f"{commit}?recursive=1"
    )


def _target_frame(
    player_history: pd.DataFrame,
    team_history: pd.DataFrame,
    bootstrap: dict,
    fixtures: list[dict],
    *,
    gameweek: int,
    understat_by_code: dict[int, int],
    understat_name_by_fpl_team: dict[str, str],
    player_marker: float,
    team_marker: float,
) -> pd.DataFrame:
    from dastan.rebuild import features

    players = build_target_player_rows(
        bootstrap,
        fixtures,
        gameweek=gameweek,
        understat_by_code=understat_by_code,
        outcome_marker=player_marker,
    )
    players["us_opponent"] = players["opponent_team_name"].map(
        understat_name_by_fpl_team
    )
    if players["us_opponent"].isna().any():
        missing = sorted(players.loc[players["us_opponent"].isna(), "opponent_team_name"].unique())
        raise RuntimeError(f"target players missing Understat opponent aliases: {missing}")
    teams = build_target_team_rows(
        bootstrap,
        fixtures,
        gameweek=gameweek,
        understat_name_by_fpl_team=understat_name_by_fpl_team,
        sentinel_base=team_marker,
    )
    full_players = pd.concat([player_history, players], ignore_index=True, sort=False)
    full_teams = pd.concat([team_history, teams], ignore_index=True, sort=False)
    frame = features.build_feature_frame(full_players, full_teams)
    frame = add_live_snapshot_features(frame, bootstrap, gameweek=gameweek)
    target = frame[
        frame["season"].eq("2026-27") & frame["gameweek"].eq(int(gameweek))
    ].copy()
    if target.empty:
        raise RuntimeError("Dastan target feature frame is empty")
    return target.sort_values(["element", "fixture"], kind="mergesort").reset_index(drop=True)


def _assert_placeholder_invariant(first: pd.DataFrame, second: pd.DataFrame) -> tuple[list[str], float]:
    from dastan import data

    if first[["element", "fixture"]].to_records(index=False).tolist() != second[
        ["element", "fixture"]
    ].to_records(index=False).tolist():
        raise RuntimeError("Dastan placeholder audit changed target row identity/order")
    features = data.shipped_features(first)
    left = first[features].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy()
    right = second[features].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy()
    delta = np.abs(left - right)
    max_diff = float(delta.max()) if delta.size else 0.0
    if not np.allclose(left, right, rtol=0.0, atol=1e-10, equal_nan=True):
        column_max = delta.max(axis=0)
        offenders = [
            (features[index], float(value))
            for index, value in enumerate(column_max)
            if float(value) > 1e-10
        ]
        offenders.sort(key=lambda item: item[1], reverse=True)
        raise RuntimeError(
            "future placeholder outcomes leaked into Dastan shipped features: "
            f"{offenders[:10]}"
        )
    return features, max_diff


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a genuine pinned Dastan H1 challenger forecast."
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--provenance", required=True, type=Path)
    parser.add_argument("--club-overlay", required=True, type=Path)
    parser.add_argument("--source-snapshot", required=True)
    parser.add_argument("--dastan-version", required=True)
    parser.add_argument("--history-commit", required=True)
    parser.add_argument("--raw-dir", type=Path, default=Path(".dastan-live/raw"))
    args = parser.parse_args()

    overlay_payload = json.loads(args.club_overlay.read_text(encoding="utf-8"))
    club_overlay = overlay_payload.get("club_overlay", [])
    if not club_overlay:
        raise SystemExit("Dastan club overlay is empty")

    official, raw_official = fetch_official_snapshot(season="2026-2027")
    if official.source_hash != str(args.source_snapshot):
        raise SystemExit(
            "Official FPL changed before Dastan generation: "
            f"expected {args.source_snapshot}, got {official.source_hash}"
        )
    bootstrap = raw_official["bootstrap"]
    fixtures = raw_official["fixtures"]
    target = target_gameweek(bootstrap)

    from dastan import data, predictor
    from dastan.rebuild import features, sources

    overlay_names = _patch_dastan_identity(club_overlay)
    _patch_vaastav_pin(args.history_commit)

    source_manifest_path = sources.download_sources(
        args.raw_dir,
        SEASONS,
        allow_missing_understat=True,
    )
    player_history, team_history, _ = sources.build_canonical_matches(args.raw_dir, SEASONS)
    current_history = player_history[player_history["season"].eq("2026-27")]
    if current_history.empty:
        raise SystemExit("Dastan rebuild produced no 2026-27 historical rows")
    max_completed = int(pd.to_numeric(current_history["gameweek"], errors="raise").max())
    if max_completed >= target:
        raise SystemExit(
            f"Dastan history pin contains target/future GW{max_completed}; target is GW{target}"
        )

    operational = pd.read_csv(
        data.ROOT / "data" / "mappings" / "current_fpl_understat_players.csv"
    ).rename(columns={"understat_player_id": "understat_id"})
    understat_by_code = mapping_by_fpl_code(operational.to_dict("records"))

    understat_names = {
        str(team["name"]): features.fpl_to_understat(str(team["name"]))
        for team in bootstrap.get("teams", [])
    }
    understat_names.update(overlay_names)

    first = _target_frame(
        player_history,
        team_history,
        bootstrap,
        fixtures,
        gameweek=target,
        understat_by_code=understat_by_code,
        understat_name_by_fpl_team=understat_names,
        player_marker=0.0,
        team_marker=1_000_000.0,
    )
    second = _target_frame(
        player_history,
        team_history,
        bootstrap,
        fixtures,
        gameweek=target,
        understat_by_code=understat_by_code,
        understat_name_by_fpl_team=understat_names,
        player_marker=987_654.0,
        team_marker=9_000_000.0,
    )
    feature_columns, invariant_max_diff = _assert_placeholder_invariant(first, second)

    model = predictor.Dastan()
    predicted = model.predict_frame(first, with_parts=True)
    rows = aggregate_prediction_rows(predicted, bootstrap, fixtures, gameweek=target)
    generated_at = datetime.now(timezone.utc).isoformat()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "player_id",
        "gameweek",
        "xp",
        "generated_at",
        "provider_version",
        "source_snapshot",
        "scoring_rules_version",
        "expected_minutes",
        "p_any",
        "p60",
        "coverage_status",
        "coverage_reason",
    ]
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row,
                    "generated_at": generated_at,
                    "provider_version": args.dastan_version,
                    "source_snapshot": args.source_snapshot,
                    "scoring_rules_version": SCORING_RULES_VERSION,
                }
            )

    forecast_rows = sum(row["coverage_status"] == "FORECAST" for row in rows)
    no_forecast_rows = len(rows) - forecast_rows
    model_manifest = data.ROOT / "models" / "artifact_manifest.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    feature_values = first[feature_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    feature_hash = hashlib.sha256(
        feature_values.to_csv(index=False, float_format="%.12g").encode("utf-8")
    ).hexdigest()
    provenance = {
        "schema_version": 1,
        "provider": "dastan",
        "provider_version": args.dastan_version,
        "scoring_rules_version": SCORING_RULES_VERSION,
        "generated_at": generated_at,
        "target_gameweek": target,
        "source_snapshot": args.source_snapshot,
        "official_raw_hashes": raw_official.get("raw_hashes", {}),
        "history_commit": args.history_commit,
        "history_seasons": SEASONS,
        "max_completed_history_gameweek": max_completed,
        "club_overlay_sha256": _sha256(args.club_overlay),
        "club_overlay": club_overlay,
        "dastan_artifact_manifest_sha256": _sha256(model_manifest),
        "download_manifest": source_manifest,
        "target_fixture_feature_rows": len(first),
        "official_players": len(bootstrap.get("elements", [])),
        "forecast_rows": forecast_rows,
        "no_forecast_rows": no_forecast_rows,
        "shipped_feature_count": len(feature_columns),
        "target_feature_matrix_sha256": feature_hash,
        "placeholder_invariance_max_abs_diff": invariant_max_diff,
        "output_sha256": _sha256(args.output),
    }
    args.provenance.parent.mkdir(parents=True, exist_ok=True)
    args.provenance.write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "target_gameweek": target,
                "official_players": len(rows),
                "forecast_rows": forecast_rows,
                "no_forecast_rows": no_forecast_rows,
                "feature_rows": len(first),
                "placeholder_invariance_max_abs_diff": invariant_max_diff,
                "output": str(args.output),
                "provenance": str(args.provenance),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
