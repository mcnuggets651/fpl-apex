from __future__ import annotations

import argparse
import json

from apex.sources.evidence import collect_v2_evidence


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Acquire V2 deadline evidence before the immutable snapshot freeze."
    )
    parser.add_argument("--sources", required=True)
    parser.add_argument("--records", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--season", default="2026-2027")
    parser.add_argument("--expected-official-hash", default=None)
    args = parser.parse_args()

    result = collect_v2_evidence(
        sources_path=args.sources,
        records_path=args.records,
        manifest_path=args.manifest,
        expected_official_hash=args.expected_official_hash or None,
        season=args.season,
    )
    print(
        json.dumps(
            {
                "completed": result.manifest["completed"],
                "target_gameweek": result.manifest["target_gameweek"],
                "record_count": result.manifest["record_count"],
                "hard_exclude_count": result.manifest["hard_exclude_count"],
                "audit_only_count": result.manifest["audit_only_count"],
                "required_source_failures": result.manifest[
                    "required_source_failures"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
