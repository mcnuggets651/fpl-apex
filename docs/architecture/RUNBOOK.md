# Apex V2 Operations Runbook

## Normal production attempt
`Apex V2 Production` creates an intent release, captures a canonical Official FPL pre-provider hash, regenerates AIrsenal, reacquires/final-validates Official FPL state, requires the pre/post hashes to match, freezes one snapshot, solves offline and publishes a completed final release. A BLOCKED final is a successful operational run with an unusable football decision; an orphaned intent is an operational failure.

## Exact current team state
Discretionary transfer planning requires the live editable team state from Official FPL, not merely the last public deadline squad. During the final Official re-anchor/freeze step, Apex may read one of the following GitHub Actions secrets:

- `FPL_SESSION_COOKIE`: the complete authenticated FPL browser-session cookie header value; or
- `FPL_X_API_AUTHORIZATION`: the current FPL access token. Apex adds `Bearer ` if the stored value does not already contain it.

These credentials are passed only to the Official team-state acquisition step. They must never be committed, printed, attached to artifacts, passed to forecast providers or made available to the offline solve phase.

When a credential is present Apex first calls Official `/me/` and requires the returned entry to equal the configured Apex entry. It then calls Official `/my-team/{entry_id}/` and requires 15 unique players in the frozen Official player universe, exact purchase and selling prices, non-negative bank state, and coherent transfer state. Each returned selling price is independently checked against the FPL half-profit rule and the same frozen Official market-price snapshot used by the attempt.

If a configured credential is rejected, belongs to another entry, produces incomplete price state or disagrees with the frozen Official price surface, acquisition fails closed. There is no silent downgrade to the public squad in that case.

If neither secret is configured, Apex deliberately falls back to the last public deadline picks. That public state may still support a legal HOLD/XI/captain decision, but `state_complete_for_transfers` remains false unconditionally because public picks cannot prove that no transfer has been made since the deadline. Discretionary transfer optimisation is therefore withheld.

A current `my-team` transfer state with an unlimited transfer window (for example Wildcard/Free Hit or another null-limit state) is also not treated as an ordinary free-transfer state. Apex freezes the current squad/prices but marks transfer state incomplete until chip-aware optimisation is explicitly supported.

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
Record an `ExecutionDecision` override referencing the immutable system-decision hash. Never rewrite the original system decision. The overlay must update exact bank cash flow, purchase/selling-price ownership and remaining current-period free transfers; it may remain complete only when the incoming state was already exact. Future Official reconciliation supersedes the overlay when a new authenticated team state is frozen.

## Provider promotion
Promotion is a separate governance change. A model cannot self-promote from evaluation output. Update provider authorization only in reviewed source/config and publish the rationale/evidence as a governance release.
