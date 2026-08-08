# Apex FPL — Known Issues / Boundaries

## K001 — Unpublished private FPL drafts are not public
Before a deadline, public FPL endpoints may not expose the manager's current private draft/transfers. Use explicit manual overrides or a current screenshot when supplied.

## K002 — Preseason/new-season sample uncertainty
Before competitive 2026/27 data accumulates, expected minutes, tactical roles and attacking rates rely more heavily on priors/preseason. Confidence must reflect this.

## K003 — Market odds not assumed available
Do not claim betting-market information is in production unless a validated feed is present and passes the production gate. It remains a planned high-value enhancement otherwise.

## K004 — Elite is not yet proven superior
Elite 10.0 code is merged and tested, but software CI success is not evidence that its squad selections outperform Pinnacle. The first post-merge live benchmark remains required.

## K005 — Value bias versus premium bias
The old failure mode was excessive cheap/value selection. Elite intentionally corrects this, but the opposite failure mode—over-rewarding famous premiums—must be monitored through raw-xP regret and no-hindsight evaluation.

## K006 — Model confidence is not outcome probability
A confidence score describes evidence/model stability, not a 99% chance that a squad outscores alternatives or wins FPL.

## K007 — Web evidence can drift
News/manager/transfer information changes quickly. Use freshness and authoritative sources; never let stale web claims overwrite canonical identity.

## K008 — Historical covariance/uncertainty priors
Early-season stochastic coefficients may be priors before sufficient 2026/27 outcomes exist. Validate them as the no-hindsight archive grows.

## Resolution discipline
When an issue is fixed, retain the entry and mark it resolved with date, implementation and benchmark evidence rather than deleting it.
