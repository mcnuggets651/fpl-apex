#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from apex_fpl.services.decision_bundle import DecisionBundle
from apex_fpl.services.selection_reality_evidence import materialize_selection_reality_evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", default="data/generated/decision_bundle")
    parser.add_argument("--output-dir", default="data/generated")
    parser.add_argument("--specialist", default="data/manual/specialist_predictions.csv")
    parser.add_argument("--transfer", default="data/manual/transfer_checks.csv")
    args = parser.parse_args()

    bundle = DecisionBundle.load(args.bundle_dir)
    players = bundle.to_pipeline_output().players
    specialist, transfer = materialize_selection_reality_evidence(
        players,
        specialist_path=Path(args.specialist),
        transfer_path=Path(args.transfer),
        output_dir=Path(args.output_dir),
    )
    print(
        f"materialized specialist_rows={len(specialist)} transfer_rows={len(transfer)}"
    )


if __name__ == "__main__":
    main()
