# Sealed decision bundle

## Purpose

Every production decision layer must consume one immutable input surface. The
bundle prevents Pinnacle, Elite, CVaR, regret and parity diagnostics from silently
using different retrieval times, configuration, evidence or projection matrices.

The bundle contract is `apex-decision-bundle-v1`. Its content-addressed
`bundle_id` covers:

- code and configuration surface hashes;
- decision settings and source-configuration fingerprints;
- Official FPL bootstrap and fixture hashes;
- pinned upstream revisions;
- FPL Core, prior-season, preseason, Elo, tactical, news, Understat, AIrsenal,
  market and fixture-surface hashes;
- the exact player universe and player/Gameweek projection matrix;
- gameweeks and current team-state identity.

Credentials and source URLs are never persisted. Only configuration counts,
booleans and cryptographic fingerprints are recorded.

## Production sequence

1. `scripts/build_decision_bundle.py` performs all retrieval and projection work once.
2. `scripts/run_pinnacle.py` loads the bundle and performs no retrieval.
3. `scripts/run_elite.py` loads the same bundle and performs no retrieval.
4. Independent solver parity records the same `bundle_id` and projection hash.
5. The canonical builder rejects missing or mismatched bundle identities.

`scripts/run_apex.py` orchestrates this sequence. `--force` applies only to bundle
creation; it is never forwarded to a diagnostic consumer.

## Audit and replay

Validate lineage and artifact hashes:

```bash
python scripts/audit_decision_bundle.py data/generated/decision_bundle
```

Replay the decision layers without network retrieval:

```bash
python scripts/replay_decision_bundle.py \
  data/generated/decision_bundle \
  --output-dir data/generated/replay
```

The bundle is retained in production workflow artifacts. Replays use the sealed
creation timestamp so repeated runs do not acquire artificial output differences
from wall-clock metadata.

## Failure rules

- A missing manifest or frame is a hard failure.
- A changed byte in a persisted frame is a hard failure.
- A changed material input produces a different `bundle_id`.
- A parity result from another bundle cannot be embedded.
- Pinnacle and Elite from different bundles cannot produce a canonical team.
- A legacy diagnostic without a bundle ID is not accepted when a bundle is
  supplied to the canonical production path.
