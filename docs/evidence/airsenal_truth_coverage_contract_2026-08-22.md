# AIrsenal truth coverage contract

Date: 2026-08-22

## Purpose

Production must distinguish **raw upstream source presence** from **certified projection coverage**. AIrsenal can legitimately omit newly added or otherwise unsupported FPL player/Gameweek pairs. Apex must never fabricate an AIrsenal projection to make that raw coverage look complete.

## Contract

For every player/Gameweek pair in the sealed official FPL universe, exactly one of these states must hold:

1. **AIrsenal present** — `source_present_airsenal=true` and the configured AIrsenal contribution is used normally.
2. **AIrsenal explicitly source-absent and reconciled** — the pair is marked `airsenal_source_absent=true`, the AIrsenal source weight is not presented as an AIrsenal value, and the configured missing-source weight is transparently delegated to the governed Apex fallback through a positive `effective_weight_airsenal_fallback_apex` contribution.

Anything else is a production blocker.

## Published metrics

- `airsenal_raw_projection_pair_coverage`: fraction of expected pairs containing a genuine upstream AIrsenal projection.
- `airsenal_projection_pair_coverage`: certified pair coverage. A pair counts only when AIrsenal is genuinely present or its absence is explicitly reconciled under the governed fixed-weight fallback contract.
- `airsenal_source_absence_reconciled`: true only when every raw source-absent pair is reconciled.
- `airsenal_source_absent_pair_count`: number of raw upstream omissions.
- `airsenal_unreconciled_source_absent_pair_count`: number of omissions that fail the fallback contract.

Production gates continue to require `airsenal_projection_pair_coverage == 1.0`. This does **not** mean raw upstream AIrsenal presence must be 100%; it means the entire sealed player/Gameweek universe must have a truthful, governed treatment of the AIrsenal component.

## Fail-closed cases

Publication is rejected when any expected pair is missing canonical projection coverage, when an AIrsenal-absent pair lacks the explicit source-absence marker, when its governed fallback weight is absent/non-positive, or when the all-player truth audit otherwise reports blockers.

This contract preserves both requirements: no fabricated expert data and no silently missing ensemble contribution.
