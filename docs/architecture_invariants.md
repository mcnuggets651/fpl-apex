# Apex FPL architecture invariants

This document is the production contract for the Apex decision engine. It exists to
prevent the system becoming a collection of individually reasonable stages whose
combined semantics are ambiguous.

## 1. One decision surface

A deadline decision is built once and sealed as a DecisionBundle. Every downstream
model, optimiser, audit, robustness layer and publication gate must consume the exact
same sealed player rows, projection rows, evidence rows, official snapshot lineage,
upstream pins and decision parameters.

A later process must not silently re-read ambient configuration and call that the
same surface. For bundle-backed audits, budget, club limit, decay, shortlist policy
and exact-candidate parameters come from the bundle manifest. A changed configuration
requires a newly sealed bundle.

## 2. Official FPL owns game identity and legality

Official FPL is canonical for player ID, club, position, live price, availability
status, fixture identity and deadline structure. Auxiliary sources can enrich a
player but must never overwrite canonical identity by name matching.

A production projection surface is complete only when every official player has one
valid canonical player/Gameweek projection state for every actionable Gameweek.
Unknown IDs, duplicate player/Gameweek keys and non-finite projections fail closed.

## 3. Source presence is not source authority

Each quantitative source has three distinct states:

1. **raw present** — a row exists and is retained for provenance;
2. **usable expert opinion** — the source is semantically capable of contributing;
3. **governed fallback** — a nominal source weight is explicitly reassigned by a
   documented policy because the source abstained.

These states must never be conflated.

For AIrsenal specifically, the raw export remains a complete official-player/GW
matrix. A structurally all-zero multi-week surface for an entire current Premier
League club is an upstream abstention, not a forecast that every player will score
zero. The worker records this explicitly. Apex preserves the raw values for audit,
removes the unsupported rows from expert voting, and applies the existing Apex
fallback at the nominal AIrsenal weight. The 100% raw coverage requirement is not
lowered.

A zero for an individual reserve player remains a valid zero when the same club has a
real non-zero AIrsenal surface. Structural abstention is therefore detected at the
club/horizon level, not by banning zero values generally.

## 4. Missingness must be explicit

No pipeline stage may convert unavailable evidence to zero unless zero is genuinely
the modeled value. This applies to xP, expected minutes, previous-season sample,
preseason events, source disagreements and market data.

Diagnostic disagreement exists only where both sources supplied usable opinions.
An abstention is reported as non-comparable, not as an enormous disagreement against
zero.

## 5. Expected value and uncertainty are separate

Canonical `xp` is the expected-points surface. Uncertainty, evidence weakness and
robustness diagnostics may inform confidence, scenario analysis and publication
readiness, but they do not silently redefine expected value.

Hard player exclusion is reserved for adverse football evidence or FPL illegality.
Generic confidence floors are diagnostic unless separately promoted by a tested
policy decision. This is why the legacy confidence-gated comparator may be
mathematically infeasible while the EV-first production policy remains valid.

## 6. Gate statuses have typed meanings

A non-success status must identify what failed:

- **mathematically infeasible** — the specified constraints admit no solution;
- **solver inconclusive/limit** — no mathematical conclusion was proved;
- **diagnostic comparator infeasible** — an obsolete/challenger policy cannot form a
  legal decision, which is itself a diagnostic result;
- **production policy failure** — the policy intended to support publication did not
  solve or did not satisfy its certificate;
- **publication blocker** — data/evidence/reality/readiness prevents action even if a
  mathematical solution exists.

A comparator failure must never crash the pipeline as though the production policy
failed. Conversely, a timeout must never be relabeled as mathematical infeasibility.

## 7. "Exact" has a scope

`optimise_exact_horizon_decision` is exact for FPL XI, captain/vice and autosub
mechanics over the squads generated into its candidate shortlist. Its `Optimal`
status does not by itself prove global squad optimality outside that shortlist.

Production launch certification therefore depends on the broader joint-path
convergence machinery: adaptive rank-prefix evaluation, solver-bound pruning,
GW1-floor enforcement, stable-winner certification and the mandatory broader retry
when an in-solve certificate is absent. Publication must not promote a narrow
shortlist merely because its internal mechanics were solved exactly.

## 8. Transfer planning is stateful and fail-closed

The planner must obey current season free-transfer state transitions, hit costs,
manager-specific selling prices for the current squad, budget and squad legality.
Solver limits are distinct from infeasibility. A limited candidate may be pruned only
when its certified objective upper bound cannot tie or beat the incumbent; otherwise
planning is inconclusive and publication is withheld.

Future price movements are unknown at deadline time. Plans use the live snapshot and
must be rebuilt before every later deadline rather than being treated as promises.

## 9. Evidence cannot silently become model truth

Specialist predicted XIs, transfer reports and editorial opinion are corroboration and
challenge layers. They can trigger review, evidence-state changes or publication
blocks only through their explicit contracts. They do not directly mutate official
identity, xP, set pieces, minutes or tactical roles unless a separately governed
source class permits that operation.

Every material manual/official evidence item must carry source, retrieval time and
expiry semantics. Expired evidence cannot affect a fresh deadline decision.

## 10. Bundle publication is validated before promotion

Production bundle construction writes into a sibling staging directory, then reopens
and fully validates the persisted bundle. Only validated bytes are promoted to the
canonical path. A failed capture leaves the previous valid target untouched; a crash
during final promotion can produce a missing target but not a stale manifest mixed
with partially replaced frames.

Downstream loaders still verify artifact hashes, semantic dataframe hashes, settings,
metadata, official snapshot lineage and material-input lineage.

## 11. Publication is one-way and fail-closed

The user-facing pipeline is:

`sealed surface -> diagnostics -> truth gates -> mathematical selection -> football
reality -> final selected-player evidence -> actionable recommendation`

Intermediate artefacts are not recommendations. If any required final gate fails,
`ready_to_act=false`, `safe_to_act=false` where applicable, and the user-facing
recommendation is removed. A green engineering workflow is necessary but not
sufficient evidence that the football decision is ready.

## 12. Testing requirements

Every architecture invariant above requires an executable regression test whenever a
small deterministic fixture can represent it. At minimum CI must cover:

- official-ID and complete player/GW source contracts;
- AIrsenal whole-club structural abstention versus legitimate individual zeroes;
- raw-xP preservation and governed fallback behavior;
- bundle tamper detection and validated staging promotion;
- bundle-backed decision-parameter binding;
- diagnostic comparator infeasibility versus production-policy failure;
- exact FPL XI/captain/vice/autosub mechanics;
- transfer state transitions, solver-limit semantics and objective-bound pruning;
- stale/expired evidence fail-closed behavior;
- canonical publication removal after any required downstream gate failure.

Thresholds are not changed merely to make these tests green. When a test exposes a
real contract violation, the implementation is repaired or the system stays blocked.
