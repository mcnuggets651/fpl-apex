# Apex FPL — Known Issues / Boundaries

Operating authority: [`APEX_OPERATING_MANUAL.md`](APEX_OPERATING_MANUAL.md).

This file contains **current unresolved boundaries** plus a short resolved-history section. Historical implementation narratives belong in Git/`SESSION_LOG.md`, not in active issue descriptions.

## K000 — Governance gate

`data/generated/apex_answer_context.json` is the only permitted source for an Apex-labelled recommendation. If it is stale, mismatched, `safe_to_act=false` or `ready_to_act=false`, Apex publishes no team.

## K001 — Unpublished private manager state is not public

Public FPL endpoints cannot reveal unpublished private transfers/drafts. If the user has made newer private moves, exact current-state evidence is required before a transfer solve can be authoritative.

## K002 — Early-season/new-role uncertainty

2026/27 samples are still small. Minutes, roles and attacking rates can move materially with team selection, injuries and transfers. Do not manufacture certainty; keep current evidence attributable and time-bounded.

## K003 — Market odds are not production authority

Do not claim market probabilities are in production unless a validated feed is configured, fresh, mapped to the exact player/fixture surface and formally promoted. Current production market xP weight is zero.

## K004 — Apex proprietary xP is unqualified for production

Apex's proprietary forecast is shadow-only after the 28 August authority cutover. It may be diagnostically better or worse for individual players without gaining production authority.

Promotion requires genuine prospective frozen forecasts and the governed evidence threshold. Current calibration has 0 completed genuine Gameweeks / 0 active rows.

## K005 — Prospective deadline archive is not yet operating correctly

The tracked repository has no `data/history/deadlines` archive even though GW1 is complete, and the calibration report remains empty. This is a real operational gap: post-GW1 provider comparison cannot become authoritative until pre-deadline forecast rows are durably frozen and later joined to Official outcomes.

Repair must preserve the no-hindsight firewall; known post-event values cannot be backfilled and labelled prospective.

## K006 — Current AIrsenal file must be refreshed before final execution

The audited tracked `data/generated/airsenal.csv` was generated on 26 August 2026. The final production cutover requires a fresh pinned AIrsenal run with complete current player/Gameweek coverage before any recommendation can be actionable.

## K007 — FPL Core current pin must be refreshed through the repaired workflow

The old production blocker was not bad Core data. A 28 August candidate achieved 616/616 Official ID coverage and passed semantic/upstream validation, but publication invalidation failed because the workflow had not installed the Apex package.

The workflow is repaired on the cutover branch. After merge it must run again against the then-current Core candidate; do not manually pin an unvalidated later revision.

Core is enrichment rather than canonical xP authority, so its outage/staleness is a disclosed warning unless a future promoted production component depends on it.

## K008 — Understat is enrichment/shadow and can be independently unavailable

Understat remains useful for priors/research but is not a production-xP dependency. Empty/malformed football payloads are explicitly unhealthy. A temporary outage must be reported without blocking an otherwise independent AIrsenal decision path.

## K009 — Robustness/scenario parameters are not outcome-calibrated production forecasts

CVaR/correlated scenario coefficients and captain-frequency telemetry remain robustness diagnostics. They must not be interpreted as calibrated probabilities or used to override canonical EV without explicit promotion evidence.

## K010 — Historical replay has evidence limits

Historical replay remains constrained by the availability of genuinely pre-deadline Apex artifacts. Never fill missing historical decision surfaces with post-event proxies and call the result no-hindsight.

## K011 — V2 stack requires authority rebase/requalification

Draft PRs #67–#88 are engineering work, not current production. Later V2 documentation still assumes the retired fixed Apex/Official/AIrsenal blend. Before any future V2 merge/cutover, the stack must be rebased and requalified against the current AIrsenal-only production forecast authority.

Synthetic/CI mechanism evidence cannot substitute for genuine production/empirical qualification.

## K012 — Price-change prediction is not production truth

Current Official price is factual. Future price changes may be modelled as planning context only after a validated prediction feed/model exists. Do not alter current legality using speculative future price moves.

## Resolved 2026-08-28

- **R001 — FPL Core publication import failure:** root cause identified as missing package installation in `refresh-core-pin.yml`; workflow now installs Apex and verifies the publication import path before validation/publication.
- **R002 — False Core/Understat production criticality:** production dependency graph changed so optional enrichment does not block canonical AIrsenal xP.
- **R003 — Hand-set production forecast blend:** retired. Production xP is one-hot AIrsenal; Apex is shadow.
- **R004 — Expired GW1 workflow:** `gw1-final-2026.yml` archived and removed from the active workflow surface.
- **R005 — Stale current-state documentation:** pre-GW1/current-team claims in status/architecture/model/source docs replaced with the audited authority contract.

## Resolution discipline

When a current issue is fixed, move it into the resolved section with date and evidence. Do not keep contradictory active and resolved descriptions under duplicate issue IDs.
