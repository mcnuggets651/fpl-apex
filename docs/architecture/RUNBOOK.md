# Apex V2 Operations Runbook

## Normal production attempt
`Apex V2 Production` creates an intent release, captures a canonical Official FPL pre-provider hash, regenerates AIrsenal, reacquires/final-validates Official FPL state, requires the pre/post hashes to match, freezes one snapshot, solves offline and publishes a completed final release. A BLOCKED final is a successful operational run with an unusable football decision; an orphaned intent is an operational failure.

## If AIrsenal fails
Do not substitute cached xP. If an explicitly authorized standby has a fresh complete qualified H1 surface in the same frozen attempt, serving selection may use it. Otherwise final certification is BLOCKED. Shadow providers do not rescue production.

## If Dastan/OpenFPL fail
No production effect while they are non-serving challengers. Record failure in provider diagnostics.

## If Official FPL changes during acquisition
Provider generation is bracketed by the same canonical Official FPL hash function used by Apex (`bootstrap-static` plus fixtures). If the post-provider hash differs from the pre-provider hash, abort the attempt before team/provider qualification or freeze. Do **not** accept the later state and relabel the provider as though it had used that state. Start a new run/intent and regenerate the provider from a fresh Official seal. Matching pre/post hashes are persisted in `run.json` and snapshot metadata.

## If the solver fails
Do not rerun against newly fetched data under the same attempt. The frozen snapshot is the evidence. Fix/retry code only under a new intent/run ID unless the operation is a deterministic retry of the identical code+snapshot and is explicitly linked in forensic records.

## If publication fails
The intent remains visible. The evaluator must flag it after the grace period. Do not rewrite an old final tag; create a new run attempt.

## If a user executes a different decision
Record an `ExecutionDecision` override referencing the immutable system-decision hash. Never rewrite the original system decision. Future team-state reconciliation overlays the execution record rather than pretending the system predicted it.

## Provider promotion
Promotion is a separate governance change. A model cannot self-promote from evaluation output. Update provider authorization only in reviewed source/config and publish the rationale/evidence as a governance release.
