# Apex V2 Operations Runbook

## Normal production attempt
`Apex V2 Production` creates an intent release, captures a canonical Official FPL pre-provider hash, regenerates AIrsenal, reacquires/final-validates Official FPL state, requires the pre/post hashes to match, freezes one snapshot, solves offline and publishes a completed final release. A BLOCKED final is a successful operational run with an unusable football decision; an orphaned intent is an operational failure.

The production AIrsenal worker runs inside the exact pinned AIrsenal environment and sets `AIRSENAL_REQUIRE_MINUTE_MARGINALS=1`. The standalone exporter may omit minute marginals only for backwards-compatible identity tooling outside that worker. Production must never rely on that compatibility mode. Single-fixture rows must carry the model-derived `expected_minutes`, `p_appearance` and `p_60`; a multi-fixture Gameweek may intentionally leave the joint appearance probability blank and will therefore stop the contingency-qualified decision horizon there.

## Exact current team state
Discretionary transfer planning requires the live editable team state from Official FPL, not merely the last public deadline squad. During the final Official re-anchor/freeze step, Apex may read one of the following GitHub Actions secrets:

- `FPL_SESSION_COOKIE`: the complete authenticated FPL browser-session cookie header value; or
- `FPL_X_API_AUTHORIZATION`: the current FPL access token. Apex adds `Bearer ` if the stored value does not already contain it.

These credentials are passed only to the Official team-state acquisition step. They must never be committed, printed, attached to artifacts, passed to forecast providers or made available to the offline solve phase.

When a credential is present Apex first calls Official `/me/` and requires the returned entry to equal the configured Apex entry. It then calls Official `/my-team/{entry_id}/` and requires 15 unique players in the frozen Official player universe, exact purchase and selling prices, non-negative bank state, and coherent transfer state. Each returned selling price is independently checked against the FPL half-profit rule and the same frozen Official market-price snapshot used by the attempt.

If a configured credential is rejected, belongs to another entry, produces incomplete price state or disagrees with the frozen Official price surface, acquisition fails closed. There is no silent downgrade to the public squad in that case.

If neither secret is configured, Apex deliberately falls back to the last public deadline picks. That public state may still support a legal HOLD/XI/captain decision, but `state_complete_for_transfers` remains false unconditionally. Official FPL's public transfer-history UI states that other viewers can see transfers only up to the last deadline, so an unauthenticated current-period absence of transfer rows is not evidence that the manager made no transfer. Discretionary transfer optimisation is therefore withheld.

Every frozen snapshot records this boundary explicitly. `team_state_acquisition.json` contains the non-secret acquisition mode (`AUTHENTICATED_MY_TEAM`, `PUBLIC_DEADLINE_FALLBACK` or `NO_PUBLIC_DEADLINE`), whether a credential was present, exact-price counts and public-ledger diagnostics. `team_transfers_public.json` freezes the public transfer ledger as historical evidence. The ledger may support retrospective reconstruction after a deadline, but it never upgrades a deadline-redacted pre-deadline state to transaction-safe by itself. Credentials, cookies and authorization headers are never serialized.

A current `my-team` transfer state with an unlimited transfer window (for example Wildcard/Free Hit or another null-limit state) is also not treated as an ordinary free-transfer state. Apex freezes the current squad/prices but marks transfer state incomplete until chip-aware optimisation is explicitly supported.

## Contingency-model checks
Two horizons must be inspected separately on every attempt:

- `max_contiguous_qualified_horizon` is the contiguous authorized serving-xP horizon;
- `contingency_qualified_horizon` is the stricter contiguous horizon over which every decision-universe player has the appearance inputs required for exact autosub and vice-captain valuation.

H1 contingency completeness is mandatory. If it is zero or the certification includes `CONTINGENCY_MODEL_INCOMPLETE`, the attempt is not actionable even if serving xP is otherwise complete. Do not downgrade this to a warning. Missing later-horizon appearance inputs are allowed only by truncating transfer planning to the last contingency-qualified horizon.

For a fixed squad, exact mechanics must satisfy all of the following:

- goalkeeper replacement is valued only through the bench goalkeeper;
- outfield substitutes enter in submitted priority order and only when the resulting formation remains FPL-legal;
- captain/vice fallback uses unconditional provider xP and adds the vice copy only in the captain no-show state;
- an active H1 `HARD_EXCLUDE` forces both contingency appearance probability and effective contingency xP to zero;
- the submitted EV reconciles to XI xP + exact expected autosub value + exact expected captain/vice bonus.

The transfer/initial-squad MILP remains the bounded primary-xP candidate generator. Inspect `decision_optimisation.solver` for candidate count, primary optimum/regret floor, shortlist completeness and final selection mode. Exact contingency rescoring may replace the primary candidate only when the governed regret-band shortlist is proven complete. If the candidate cap was reached before proof of completeness, the final selection must be the original primary-EV candidate and diagnostics must say so. Never interpret a capped shortlist as a certified exhaustive secondary search.

Command Center may expose the wider serving horizon in Players/research views, but execution and plan surfaces must stop at `contingency_qualified_horizon`.

## Cutover platform controls
V2 cutover is not permitted merely because code CI is green. `config/apex_v2_cutover_platform.yaml` is the machine-readable repository-control contract and `.github/workflows/apex-v2-cutover-platform.yml` freezes live GitHub evidence and certifies it with `scripts/check_v2_cutover_platform.py`.

Before cutover, configure an **active repository branch ruleset** targeting `main` (either `refs/heads/main` or `~DEFAULT_BRANCH`) with no bypass actors and all of the following rules:

- restrict deletion (`deletion`);
- block non-fast-forward updates / force pushes (`non_fast_forward`);
- require changes through pull requests (`pull_request`); and
- require strict/up-to-date status checks (`required_status_checks`).

The required status-check contexts are the GitHub Actions **job names**, exactly:

- `test` — full Apex CI;
- `contract` — Apex V2 contract suite; and
- `readiness` — projection-policy audit.

All three must be required simultaneously. A ruleset containing only one or two, a ruleset in evaluate/disabled mode, a ruleset excluding `main`, or a ruleset with bypass actors does not satisfy Apex cutover.

Also enable **release immutability** in repository Settings → Releases → **Enable release immutability**. The cutover workflow checks GitHub's canonical `/repos/{owner}/{repo}/immutable-releases` setting endpoint; HTTP 200 with `enabled=true` is required. HTTP 404 means the setting is disabled. A permission/transport failure is treated as unverifiable and blocks cutover rather than being assumed safe.

Run **Apex V2 Cutover Platform** manually from `agent/apex-v2-cleanroom` after those settings are configured. The workflow freezes:

- `main_branch.json`;
- the ruleset index and each full ruleset definition;
- `immutable_releases.json` plus its HTTP status; and
- `platform_certification.json`.

The evidence artifact is retained for 90 days. `platform_ready=true` is required before the V2 cutover PR can be considered eligible. The workflow is deliberately separate from ordinary development CI: platform settings being off must block production cutover, not prevent continued development of the draft PR.

Current repository controls must be checked live; do not infer them from documentation or an earlier successful run. Release immutability protects only releases created after the setting is enabled, so no pre-setting release is accepted as proof.

## Authenticated dress rehearsal inspection
Before cutover, the authenticated production rehearsal must be run on the exact candidate head and the resulting immutable public/private records inspected together. Require all of the following before accepting the rehearsal:

1. `APEX_CODE_SHA` equals the current PR head and the frozen run identity uses that SHA.
2. `/me/` bound the credential to the configured entry and `/my-team/{entry_id}/` supplied the current 15-player editable squad, purchase/selling prices, bank, FT state and active chip state.
3. The private-store preflight succeeded before owner credentials were consumed; the repository is separate, private, initialized and has native release immutability enabled.
4. The private manager release was persisted and verified before the public final release.
5. Public `official_snapshot_sha256` and `canonical_projection_sha256` are non-empty 64-hex hashes and match the sealed DecisionBundle identities.
6. Evidence acquisition is complete and bound to the same target GW/Official hash; required-source failures are empty.
7. `contingency_qualified_horizon >= 1`; there is no `CONTINGENCY_MODEL_INCOMPLETE` reason; the plan contains no week beyond the contingency horizon.
8. Exact-rescore diagnostics show whether the regret-band shortlist was complete. If incomplete, verify the selected result is explicitly the primary-EV fallback rather than a secondary-rescore winner.
9. `manager_actionability` is coherent: `FULL_MANAGER` and `transfer_actionable=true` only when current editable team and exact transfer state are both verified and the decision is a valid transfer-horizon decision.
10. XI, captain, vice, bench order, transfers, hits and cash are legal under the same frozen Official snapshot; hard-excluded players contribute zero contingency value.
11. Public diagnostic/release assets contain no private manager state, purchase/selling prices, bank, FT/chip state, credentials or sentinel values.
12. Public/private attempt IDs, commitment and attestation verify without drift.

A green workflow without these sealed facts is not sufficient cutover evidence.

## If AIrsenal fails
Do not substitute cached xP. If an explicitly authorized standby has a fresh complete qualified H1 surface in the same frozen attempt, serving selection may use it. Otherwise final certification is BLOCKED. Shadow providers do not rescue production. A missing pinned AIrsenal package/minute model in the production worker is an explicit failure because production requires its minute marginals; do not fall back to the standalone exporter's blank compatibility mode.

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
