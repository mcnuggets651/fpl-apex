#!/usr/bin/env python3
"""Fetch and project once, then seal the complete Apex decision surface."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from apex_fpl.config import load_settings
from apex_fpl.data.http import CachedHttp
from apex_fpl.data.official import OfficialFPLClient
from apex_fpl.services.decision_bundle import DecisionBundle
from apex_fpl.services.pipeline import run_pipeline


def _with_official_identity_aliases(
    players: pd.DataFrame,
    official_players: pd.DataFrame,
) -> pd.DataFrame:
    """Retain deterministic Official-FPL name aliases on the sealed player surface."""
    required = {"player_id", "first_name", "second_name"}
    missing = sorted(required - set(official_players.columns))
    if missing:
        raise ValueError(f"Official FPL identity surface lacks required columns: {missing}")

    official_identity = official_players[
        ["player_id", "first_name", "second_name"]
    ].copy()
    official_identity["player_id"] = pd.to_numeric(
        official_identity["player_id"], errors="raise"
    ).astype(int)
    if official_identity["player_id"].duplicated().any():
        raise ValueError("Official FPL identity surface contains duplicate player IDs")

    sealed = players.drop(columns=["first_name", "second_name"], errors="ignore").copy()
    sealed["player_id"] = pd.to_numeric(sealed["player_id"], errors="raise").astype(int)
    unknown = sorted(set(sealed["player_id"]) - set(official_identity["player_id"]))
    if unknown:
        raise ValueError(
            f"Projected player surface contains IDs absent from Official FPL: {unknown[:10]}"
        )
    sealed = sealed.merge(
        official_identity,
        on="player_id",
        how="left",
        validate="one_to_one",
    )
    if sealed[["first_name", "second_name"]].isna().any().any():
        raise ValueError("Official FPL identity aliases are incomplete on sealed player surface")
    return sealed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--bundle-dir", default="data/generated/decision_bundle")
    args = parser.parse_args()

    settings = load_settings()
    output = run_pipeline(
        settings,
        horizon=args.horizon,
        scenario="both",
        force=args.force,
        plan_transfers=True,
    )

    # The projection pipeline intentionally publishes a compact player report, but
    # identity certification needs the canonical Official-FPL full-name aliases.
    # Re-open only the already-cached Official snapshot and require the exact same
    # bootstrap hash before attaching those aliases to the sealed DecisionBundle.
    official = OfficialFPLClient(CachedHttp(settings.cache_dir)).snapshot(force=False)
    expected_bootstrap = str(output.snapshot.get("bootstrap_sha256") or "")
    if official.bootstrap_sha256 != expected_bootstrap:
        raise RuntimeError(
            "Official FPL snapshot changed before DecisionBundle sealing: "
            f"pipeline={expected_bootstrap} seal={official.bootstrap_sha256}"
        )
    output.players = _with_official_identity_aliases(output.players, official.players)

    bundle = DecisionBundle.capture(
        output,
        settings,
        Path(args.bundle_dir),
        repo_root=Path(__file__).resolve().parents[1],
    )
    print(json.dumps(bundle.lineage_summary(), indent=2))


if __name__ == "__main__":
    main()
