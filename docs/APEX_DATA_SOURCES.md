# Apex FPL — Data Sources

## Source hierarchy
### Tier 1 — Canonical
**Official FPL**: player IDs, clubs, FPL positions, prices, statuses, fixtures, official points and public manager state. Identity conflicts are resolved in favour of Official FPL.

### Tier 2 — Model experts
**AIrsenal (pinned genuine upstream)**: independent expected-points expert. Must map through official FPL IDs.

**FPL Core Insights**: current underlying player statistics, preseason evidence, Elo/team-strength context and defensive-contribution evidence.

**Apex native models**: expected minutes, tactical role, attacking rates, fixture translation, clean sheets, saves, DEFCON, set pieces/penalties, bonus/BPS and ensemble uncertainty.

### Tier 3 — Historical/validation
Historical datasets (including the project's historical match/player layers) support priors, backtests and calibration. Historical evidence must not override current club/role identity.

**Independent open FPL solver**: parity check on the same ensemble-mean xP surface. It validates optimisation, not the forecast itself.

### Tier 4 — Short-lived evidence
Official club injury updates, manager press conferences/interviews, confirmed transfers and trusted news feeds inform availability, role and minutes. They are verification inputs rather than the primary selection engine.

### Tier 5 — Planned
Market odds/implied probabilities, improved Bayesian minutes, ownership/EO and price-movement signals may be added only with source validation and benchmark evidence.

## Provenance rules
- Pin upstream revisions in `upstreams.lock.json`.
- Record source timestamps/freshness in generated state where available.
- Never silently substitute a similarly named player across sources.
- Never use stale preseason/news evidence without freshness checks.
- If a required source fails, readiness gates must surface the blocker.

## Web usage policy
Web research is supplementary. Use it for current confirmations that repositories/APIs cannot know reliably (injury statements, manager comments, transfers, late team news). Do not browse first and then construct an Apex squad from articles.

## Personal state
Entry `63984` is the production personal manager state. Public picks become available after deadlines; unpublished draft changes are not visible and require explicit manual override.
