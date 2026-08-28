# Apex V2 Operations Runbook

## Normal production attempt
`Apex V2 Production` creates an intent release, regenerates AIrsenal, acquires/final-validates Official FPL state, freezes one snapshot, solves offline and publishes a completed final release. A BLOCKED final is a successful operational run with an unusable football decision; an orphaned intent is an operational failure.

## If AIrsenal fails
Do not substitute cached xP. If an explicitly authorized standby has a fresh complete qualified H1 surface in the same frozen attempt, serving selection may use it. Otherwise final certification is BLOCKED. Shadow providers do not rescue production.

## If Dastan/OpenFPL fail
No production effect while they are non-serving challengers. Record failure in provider diagnostics.

## If Official FPL changes during acquisition
The final Official fetch is authoritative. Every provider is validated against that final anchor before freeze. If identity/coverage is no longer coherent, block rather than patching IDs manually.

## If the solver fails
Do not rerun against newly fetched data under the same attempt. The frozen snapshot is the evidence. Fix/retry code only under a new intent/run ID unless the operation is a deterministic retry of the identical code+snapshot and is explicitly linked in forensic records.

## If publication fails
The intent remains visible. The evaluator must flag it after the grace period. Do not rewrite an old final tag; create a new run attempt.

## If a user executes a different decision
Record an `ExecutionDecision` override referencing the immutable system-decision hash. Never rewrite the original system decision. Future team-state reconciliation overlays the execution record rather than pretending the system predicted it.

## Provider promotion
Promotion is a separate governance change. A model cannot self-promote from evaluation output. Update provider authorization only in reviewed source/config and publish the rationale/evidence as a governance release.
