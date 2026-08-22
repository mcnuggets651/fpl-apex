# Apex FPL architecture invariants

This document is the production contract for the Apex decision engine. It exists to
prevent the system becoming a collection of individually reasonable stages whose
combined semantics are ambiguous.

## 1. One decision surface

A deadline decision is built once and sealed as a DecisionBundle. Every downstream
model, optimiser, audit, robustness layer and publication gate must consume the exact
same sealed player rows, projection rows, evidence rows, official snapshot lineage,
upstream pins, current-team state and decision parameters.

A later process must not silently re-read ambient configuration and call that the
same surface. For bundle-backed audits, budget, club limit, decay, shortlist policy
and exact-candidate parameters come from the bundle manifest. A changed configuration
or manager state requires a newly sealed bundle.

## 2. Official FPL owns game identity and legality

Official FPL is canonical for player ID, club, position, live price, availability
status, fixture identity and deadline structure. Auxiliary sources can enrich a
player but must never overwrite canonical identity by name matching.

Official fixture `id` is the immutable fixture key. Gameweek, opponent and home/away
are descriptive attributes and may legitimately repeat after rescheduling or unusual
double fixtures; they are never substitutes for Official fixture identity.

A production projection surface is complete only when every official player has one
valid canonical player/Gameweek projection state for every actionable Gameweek.
Unknown IDs, ambiguous fixture rows and non-finite projections fail closed.

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
preseason events, source disagreements, manager state and market data.

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

- **mathematically infeasible** — the specified constraints admit no solution and
  the solver supplied its mathematical infeasibility certificate;
- **solver inconclusive/limit** — no mathematical conclusion was proved;
- **diagnostic comparator infeasible** — an obsolete/challenger policy cannot form a
  legal decision, which is itself a diagnostic result;
- **production policy failure** — the policy intended to support publication did not
  solve or did not satisfy its certificate;
- **publication blocker** — data/evidence/reality/readiness prevents action even if a
  mathematical solution exists.

A comparator failure must never crash the pipeline as though the production policy
failed. Conversely, a timeout, missing status code or input error must never be
relabeled as mathematical infeasibility. Candidate-universe expansion on a bounded
MILP is permitted only after solver-certified mathematical infeasibility.

## 7. "Exact" has a scope

`optimise_exact_horizon_decision` is exact for FPL XI, captain/vice and autosub
mechanics over the squads generated into its candidate shortlist. Its `Optimal`
status does not by itself prove global squad optimality outside that shortlist.

Production launch certification therefore depends on the broader joint-path
convergence machinery: adaptive rank-prefix evaluation, solver-bound pruning,
current-GW floor enforcement, stable-winner certification and the mandatory broader
retry when an in-solve certificate is absent. Publication must not promote a narrow
shortlist merely because its internal mechanics were solved exactly.

The current submitted Gameweek bench-resilience policy is part of the feasible set,
not a post-processing preference. Deterministic EV, CVaR, transfer optimisation and
exact mechanics share the sealed policy marker. Future Gameweeks do not inherit a
current-deadline bench constraint: future actions are re-optimised at their own
deadlines.

## 8. Transfer planning is stateful and fail-closed

The engine has two lifecycle modes:

1. before GW1, optimise the initial legal XV;
2. once a public deadline squad exists, optimise from the manager's real current
   state and publish only the next executable action.

Production config identifies the manager entry. The weekly state is a required
source and is sealed into DecisionBundle identity. A public weekly state must contain
an exact 15-player squad, current bank, current free-transfer state and exact realised
selling price for all 15 players. The next action is never optimised from a fresh
£100m hypothetical squad when a real manager state exists.

For an original squad player, purchase price is reconstructed from the current
Official bootstrap using `cost_change_start` (or the captured opening-price snapshot
when available). For a later buy/re-buy, purchase price comes from the public transfer
ledger. FPL's half-profit selling-price rule is applied in tenths. From GW2 onward an
unavailable/incomplete transfer ledger makes realised selling values unprovable and
blocks actionable transfer optimisation rather than substituting current market
price.

A manual override can supersede the latest public deadline snapshot when the manager
has already changed the squad during the current Gameweek, but it is actionable only
when it supplies the exact 15, bank/free-transfer state and a realised selling price
for every player. This prevents hidden post-deadline moves from being silently
ignored.

The planner obeys current-season free-transfer state transitions, hit costs, realised
selling prices, budget and squad legality. Solver limits are distinct from
infeasibility. A limited candidate may be pruned only when its certified objective
upper bound cannot tie or beat the incumbent; otherwise planning is inconclusive and
publication is withheld.

Only the first action is executable. Future transfer paths are contingencies using
the live snapshot and must be rebuilt before every later deadline. Speculative future
price movements are not treated as known truth.

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
and fully validates the persisted bundle. Only validated bytes are promoted. A failed
capture cannot masquerade as a valid current generation.

Every production workflow writes into an initially empty run-scoped generation. A
run may not read tracked `*_latest` files as though they were outputs of the current
execution. Pinnacle, parity, recommendation, answer context and diagnostics from one
certified generation share one DecisionBundle identity and provenance chain.

Promotion updates latest aliases only from that validated generation. Main-branch
publication is compare-and-swap: if `main` changed after the solve began, the stale
writer aborts instead of rebasing its old decision onto new code/data.

Downstream loaders verify artifact hashes, semantic dataframe hashes, settings,
metadata, official snapshot lineage, manager-state lineage and material-input
lineage.

## 11. Publication is one-way and fail-closed

The user-facing pipeline is:

`sealed surface -> diagnostics -> truth gates -> mathematical selection -> exact
current-GW mechanics -> football reality -> final selected-player evidence ->
actionable recommendation`

Intermediate artefacts are not recommendations. If any required final gate fails,
`ready_to_act=false`, `safe_to_act=false` where applicable, and the user-facing
recommendation is removed. A green engineering workflow is necessary but not
sufficient evidence that the football decision is ready.

No publication wrapper may reorder the bench, replace a player or otherwise mutate a
certified recommendation. Publication independently recomputes exact mechanics from
the sealed bundle and blocks on any XI/captain/vice/bench/xP mismatch.

## 12. Testing requirements

Every architecture invariant above requires an executable regression test whenever a
small deterministic fixture can represent it. At minimum CI must cover:

- official-ID, immutable fixture-ID and complete player/GW source contracts;
- AIrsenal whole-club structural abstention versus legitimate individual zeroes;
- raw-xP preservation and governed fallback behavior;
- bundle tamper detection and validated staging promotion;
- bundle-backed decision-parameter and manager-state binding;
- diagnostic comparator infeasibility versus production-policy failure;
- exact FPL XI/captain/vice/autosub mechanics and current-bench feasibility;
- public entry squad/bank/free-transfer reconstruction and exact selling prices;
- transfer state transitions, solver-limit semantics and objective-bound pruning;
- stale/expired evidence fail-closed behavior;
- generation-coherence and compare-and-swap publication;
- canonical publication removal after any required downstream gate failure.

Thresholds are not changed merely to make these tests green. When a test exposes a
real contract violation, the implementation is repaired or the system stays blocked.
