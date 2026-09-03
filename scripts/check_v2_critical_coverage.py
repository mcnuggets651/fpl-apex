from __future__ import annotations

import argparse
import json
from pathlib import Path

MINIMUMS = {
    "src/apex/decision/mechanics.py": 90.0,
    "src/apex/decision/optimiser.py": 85.0,
    "src/apex/decision/transfers.py": 85.0,
    "src/apex/decision/validate.py": 100.0,
    "src/apex/domain/rules.py": 80.0,
    "src/apex/forecast/contract.py": 75.0,
    "src/apex/forecast/qualification.py": 80.0,
    "src/apex/governance/certification.py": 80.0,
    "src/apex/runtime/acquire.py": 90.0,
    "src/apex/runtime/config.py": 80.0,
    "src/apex/runtime/publication.py": 80.0,
    "src/apex/runtime/publication_impl.py": 70.0,
    "src/apex/runtime/serving.py": 80.0,
    "src/apex/runtime/snapshot.py": 75.0,
    "src/apex/runtime/solve.py": 75.0,
    "src/apex/sources/official.py": 80.0,
}
TOTAL_MINIMUM = 75.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("coverage_json", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.coverage_json.read_text(encoding="utf-8"))
    files = payload.get("files") or {}
    failures: list[str] = []
    for path, minimum in MINIMUMS.items():
        row = files.get(path)
        if row is None:
            failures.append(f"{path}: missing from coverage report")
            continue
        observed = float(row["summary"]["percent_covered"])
        print(f"{path}: {observed:.2f}% (floor {minimum:.2f}%)")
        if observed + 1e-9 < minimum:
            failures.append(f"{path}: {observed:.2f}% < {minimum:.2f}%")
    total = float(payload["totals"]["percent_covered"])
    print(f"TOTAL Apex V2: {total:.2f}% (floor {TOTAL_MINIMUM:.2f}%)")
    if total + 1e-9 < TOTAL_MINIMUM:
        failures.append(f"total: {total:.2f}% < {TOTAL_MINIMUM:.2f}%")
    if failures:
        raise SystemExit("critical coverage regression:\n- " + "\n- ".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
