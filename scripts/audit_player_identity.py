#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from apex_fpl.services.decision_bundle import DecisionBundle
from apex_fpl.services.player_identity import audit_identity_sources


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", default="data/generated/decision_bundle")
    parser.add_argument("--airsenal", default="data/generated/airsenal.csv")
    parser.add_argument("--specialist", default="data/manual/specialist_predictions.csv")
    parser.add_argument("--transfer", default="data/manual/transfer_checks.csv")
    parser.add_argument("--output", default="reports/player_identity_audit.json")
    parser.add_argument("--csv", default="reports/player_identity_audit.csv")
    args = parser.parse_args()

    bundle = DecisionBundle.load(args.bundle_dir)
    players = bundle.to_pipeline_output().players
    sources: dict[str, pd.DataFrame] = {}
    blockers: list[str] = []
    warnings: list[str] = []

    air_path = Path(args.airsenal)
    if bool(bundle.settings.get("source_configuration", {}).get("airsenal_configured")):
        air = _read(air_path)
        if air.empty:
            blockers.append("configured AIrsenal export is missing or empty for identity audit")
        elif "source_player_name" not in air.columns:
            blockers.append("configured AIrsenal export lacks independent source_player_name witness")
        elif "identity_witness_type" not in air.columns:
            blockers.append("configured AIrsenal export lacks identity_witness_type provenance")
        elif set(air["identity_witness_type"].dropna().astype(str)) != {"airsenal_name"}:
            blockers.append("configured AIrsenal export contains non-authoritative identity witnesses")
        else:
            sources["airsenal"] = air.drop_duplicates("player_id")

    for name, path in (
        ("fpl_specialist_manual", Path(args.specialist)),
        ("transfer_specialist_manual", Path(args.transfer)),
    ):
        frame = _read(path)
        if not frame.empty:
            sources[name] = frame.drop_duplicates("player_id")

    audit = audit_identity_sources(players, sources, require_identity_witness=True)
    blockers.extend(audit.get("blockers") or [])
    warnings.extend(audit.get("warnings") or [])
    audit["blockers"] = list(dict.fromkeys(blockers))
    audit["warnings"] = list(dict.fromkeys(warnings))
    audit["ready"] = not audit["blockers"]
    audit["decision_bundle_id"] = bundle.bundle_id

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")

    rows: list[dict] = []
    for source, result in (audit.get("sources") or {}).items():
        rows.append({"source": source, **result})
    pd.DataFrame(rows).to_csv(args.csv, index=False)
    print(json.dumps({"ready": audit["ready"], "blockers": audit["blockers"]}, indent=2))
    raise SystemExit(0 if audit["ready"] else 1)


if __name__ == "__main__":
    main()
