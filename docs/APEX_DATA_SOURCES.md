# Apex FPL — Data Sources

## Source hierarchy
### Tier 1 — Canonical
**Official FPL**: player IDs, clubs, FPL positions, prices, statuses, fixtures, official points and public manager state. Identity conflicts are resolved in favour of Official FPL.

Player identity is governed by `apex-player-identity-integrity-v2`. Current Official FPL numeric player IDs are authoritative and are never replaced by fuzzy names, aliases or provider mappings. Independent provider/manual names are corroborating witnesses only. Duplicate, null or non-numeric IDs in the Official registry are hard failures rather than rows Apex may silently de-duplicate.

### Tier 2 — Model experts
**AIrsenal (pinned genuine upstream)**: independent expected-points expert. Must map through official FPL IDs. When AIrsenal is configured for a sealed generation, its identity export is roster-complete: every current Official FPL player ID must appear and no unknown ID may appear. Every row retains an independent `source_player_name` witness with `identity_witness_type=airsenal_name`; one bad GW row cannot be hidden by a good row for the same player.

**FPL Core Insights**: current underlying player statistics, preseason evidence, Elo/team-strength context and defensive-contribution evidence.

**Apex native models**: expected minutes, tactical role, attacking rates, fixture translation, clean sheets, saves, DEFCON, set pieces/penalties, bonus/BPS and ensemble uncertainty.

### Tier 3 — Historical/validation
Historical datasets (including the project's historical match/player layers) support priors, backtests and calibration. Historical evidence must not override current club/role identity.

**Independent open FPL solver**: parity check on the same ensemble-mean xP surface. It validates optimisation, not the forecast itself.

### Tier 4 — Short-lived evidence
Official club injury updates, manager press conferences/interviews, confirmed transfers and trusted news feeds inform availability, role and minutes. They are verification inputs rather than the primary selection engine.

Official HTML indexes are followed only to same-host HTTPS article pages. Apex accepts
publication time and article copy only from structured `Article`/`NewsArticle` metadata;
retrieval time is never substituted for publication time. Automated player matching uses
full names where available and rejects ambiguous surnames unless the player's official club
is named in the article. Lineup, availability, tactical-role and set-piece evidence have
separate expiry windows. A captain or high-uncertainty starter is decision-grade only with
an official source or two independent trusted-media sources.

### Tier 5 — Planned
Market odds/implied probabilities, improved Bayesian minutes, ownership/EO and price-movement signals may be added only with source validation and benchmark evidence.

## Identity certification and diagnostics
The canonical run executes player identity certification after staging and before statistical-truth, selection-reality and player-truth gates. The audit validates every available source row against the sealed Official registry and also validates player-scoped IDs referenced by the staged canonical recommendation.

Certified runs write `player_identity_audit.json` and `player_identity_audit.csv` inside that generation's run-scoped output directory. The JSON records the DecisionBundle ID, Official snapshot ID where present, Official player count, source paths, row counts, file sizes and SHA-256 hashes, per-source resolution counts, AIrsenal roster coverage, selected-reference coverage, warnings and exact blockers. Expected input/load failures also publish a structured `ready=false` report before exiting non-zero, so a failed identity gate is inspectable rather than a bare exit code.

Identity failures remain fail-closed. A known numeric ID with a conflicting name, team or position witness blocks; an unknown ID blocks; an ambiguous name-only fallback blocks; and a roster-complete source with missing/extra Official IDs blocks. Sparse manual evidence sources are not incorrectly required to cover the whole roster, but every player-linked row they do contain must carry a valid independent name witness. Canonical strategy publication surfaces the first machine-readable identity blockers and sets actionable outputs false.

## Provenance rules
- Pin upstream revisions in `upstreams.lock.json`.
- Record source timestamps/freshness in generated state where available.
- Never silently substitute a similarly named player across sources.
- Never use stale preseason/news evidence without freshness checks.
- If a required source fails, readiness gates must surface the blocker.
- Identity reports must be run-scoped and tied to the sealed DecisionBundle/source files; ambient `reports/` aliases are not certification evidence.

## Web usage policy
Web research is supplementary. Use it for current confirmations that repositories/APIs cannot know reliably (injury statements, manager comments, transfers, late team news). Do not browse first and then construct an Apex squad from articles.

## Personal state
Entry `63984` is the production personal manager state. Public picks become available after deadlines; unpublished draft changes are not visible and require explicit manual override.