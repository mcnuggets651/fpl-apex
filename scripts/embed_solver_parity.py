#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from apex_fpl.services.pinnacle_readiness import evaluate_pinnacle_payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pinnacle", type=Path)
    parser.add_argument("parity", type=Path)
    args = parser.parse_args()

    payload = json.loads(args.pinnacle.read_text(encoding="utf-8"))
    parity = json.loads(args.parity.read_text(encoding="utf-8"))
    if parity.get("comparison_surface") != "pinnacle_ev":
        raise SystemExit("refusing to embed parity that was not computed on Pinnacle EV")
    payload["solver_parity"] = parity
    readiness = evaluate_pinnacle_payload(payload)
    payload["pinnacle_ready"] = readiness.ready
    payload["pinnacle_gate"] = readiness.to_dict()
    args.pinnacle.write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(
        f"Embedded Pinnacle EV parity: squad={parity.get('squad_overlap')}/15, "
        f"XI={parity.get('xi_overlap')}/11, captain={parity.get('captain_agrees')}"
    )


if __name__ == "__main__":
    main()
