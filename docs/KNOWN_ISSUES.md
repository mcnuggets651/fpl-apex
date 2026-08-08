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
The current transparent player projection blends established rate inputs with preseason evidence, but it does not yet apply formal empirical-Bayes shrinkage of xG90/xA90/related attacking rates toward position/role priors as a function of sample size. This matters most for transfers, role changes, injury returns and players with very small minute samples. Add and benchmark shrinkage before prioritising a new Dixon-Coles fixture expert.

## K010 — Elite epsilon is provisional, not calibrated
The 0.5% maximum raw-xP regret band is an engineering starting point, not a learned constant. Live Elite output must report a sensitivity frontier at 0%, 0.25%, 0.5% and 1.0%. If tiny epsilon changes materially alter the squad, maximum-EV remains canonical until no-hindsight calibration establishes a justified band.

## Resolution discipline
When an issue is fixed, retain the entry and mark it resolved with date, implementation and benchmark evidence rather than deleting it.
