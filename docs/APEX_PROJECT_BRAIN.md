# Apex Project Brain

## Constitutional state

- Architecture freeze: **TRUE** as of 23 August 2026.
- Production source branch at migration start: `main`.
- Historical evolutionary PR #66: reference/regression archaeology only; do not merge wholesale.
- V2 migration strategy: small vertical slices, each tested and reviewable.

## Current migration authority

Dynamic live fields such as current source SHA, world ID, release ID, model ID, source health and recommendation must come from machine manifests/registries. This document must not duplicate them as hand-maintained truth.

## Non-negotiable lessons

1. Git cannot be the live runtime database.
2. Official FPL is field-level authority for official identity/state/rules where applicable, not blanket future truth.
3. Missing decision-critical data is explicit absence, not an implicit neutral default.
4. Solver status, exactness scope and candidate-universe certification are separate claims.
5. The optimiser does not certify its own legality or mechanics.
6. Forecast uncertainty separates what is empirically qualifiable from what football makes irreducibly uncertain.
7. Replay is point-in-time and governed by first-known timestamps.
8. One canonical recommendation is published only from a certified current bundle.
