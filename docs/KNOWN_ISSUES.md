# Apex FPL — Known Issues / Boundaries

## K001 — Unpublished private FPL drafts are not public
Before a deadline, public FPL endpoints may not expose the manager's current private draft/transfers. Use explicit manual overrides or a current screenshot when supplied.

## K002 — Preseason/new-season sample uncertainty
Before competitive 2026/27 data accumulates, expected minutes, tactical roles and attacking rates rely more heavily on priors/preseason. Confidence must reflect this.

## K003 — Market odds not assumed available
Do not claim betting-market information is in production unless a validated feed is present and passes the production gate. It remains a planned high-value enhancement otherwise.

## K004 — Elite is not yet proven superior
Elite 10.0 is a secondary selector and remains under live validation. Software CI success is not evidence that its squad selections outperform Pinnacle. The synchronized post-merge live benchmark and epsilon sensitivity frontier are required before Elite can override maximum-EV.

## K005 — Value bias versus premium bias
The old failure mode was excessive cheap/value selection. Elite intentionally corrects this, but the opposite failure mode—over-rewarding famous premiums—must be monitored through raw-xP regret and no-hindsight evaluation.

## K006 — Model confidence is not outcome probability
A confidence score describes evidence/model stability, not a 99% chance that a squad outscores alternatives or wins FPL.

## K007 — Web evidence can drift
News/manager/transfer information changes quickly. Use freshness and authoritative sources; never let stale web claims overwrite canonical identity.

## K008 — Historical covariance/uncertainty priors
Early-season stochastic coefficients may be priors before sufficient 2026/27 outcomes exist. Validate them as the no-hindsight archive grows.

## K009 — Player attacking rates need explicit sample-size shrinkage
**Status: research implementation exists; production remains blocked.** The current
transparent production projection still does not apply formal empirical-Bayes
shrinkage. PR #18 merges a dormant candidate that combines previous/current
competitive evidence and hierarchical leave-one-out priors. Its corrected
attacking-rate shadow gate passes; the production-parity integration audit and
separate activation review remain outstanding.

## K010 — Elite epsilon is provisional, not calibrated
The 0.5% maximum raw-xP regret band is an engineering starting point, not a learned constant. Live Elite output must report a sensitivity frontier at 0%, 0.25%, 0.5% and 1.0%. If tiny epsilon changes materially alter the squad, maximum-EV remains canonical until no-hindsight calibration establishes a justified band.

## K011 — Source health booleans must be native Python booleans
**Resolved 2026-08-08 in PR #12.** The provenance boundary now normalises source-health fields to native Python booleans. The 70% prior-season evidence floor and strict readiness semantics were unchanged.

## K012 — PR #14 historical shrinkage validation used a future-selected cohort
**Resolved in the research validator by PR #18; production remains blocked.** The
first green validator filtered players by future minutes/outcome availability
before calculating live-price tiers and empirical priors. PR #18 freezes priors
on the complete point-in-time roster, applies outcome eligibility only after
prediction and includes pre-GW1/GW1-5/GW6+ gates. The corrected xG90/xA90 shadow
gate passes, but the seasons are not independent final holdouts and no production
activation is connected.

## K013 — Captain scenario frequencies are not calibrated probabilities
The correlated scenario coefficients are explicit priors. Fixed-XI captain frequencies are useful telemetry, but a 50% hard publication decision cannot be interpreted as calibrated probability evidence until historical coverage and discrimination are validated. The raw baseline also fails the proposed fixed-XI threshold, so this diagnostic must be separated from shrinkage promotion.

## K014 — Full-season replay path is incomplete
The live pipeline has no injected historical clock or immutable as-of bundle, and the canonical builder is still initial-squad-oriented after GW1. A season replay also needs a deterministic chip controller, realised scorer and hash-chained team state. See `FULL_SEASON_REPLAY_PROTOCOL.md`.

## Resolution discipline
When an issue is fixed, retain the entry and mark it resolved with date, implementation and benchmark evidence rather than deleting it.
