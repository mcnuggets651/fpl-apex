# Apex FPL — Data Sources

## Authority is capability-specific

Apex does not use one universal source ranking. A source is authoritative only for the capability it owns.

### Official FPL — factual authority

Official FPL is canonical for current:

- player ID;
- club;
- FPL position;
- price;
- Official availability/status fields;
- fixtures/deadlines;
- public manager-state facts exposed by the game.

Identity/price/fixture conflicts are resolved in favour of Official FPL.

### AIrsenal — production statistical xP

The pinned genuine AIrsenal worker is the current production statistical projection provider. It must map through Official FPL IDs and cover the complete required current player/Gameweek horizon.

Production `xp` is AIrsenal exactly. Missing, stale, malformed or incomplete AIrsenal is a hard production blocker. Apex proprietary xP is not a fallback.

### FPL Core Insights — enrichment

FPL Core remains an important supporting source for player statistics, prior/current samples, preseason evidence, Elo/team context and defensive-contribution evidence. Candidate revisions are semantically validated before the immutable pin moves.

Core is **not** currently a canonical-xP dependency. Its health, age and coverage must be disclosed; failure is an enrichment warning unless a future production component explicitly depends on it.

### Understat — enrichment/shadow modelling

Understat supports underlying-stat priors, player/team research and Apex shadow modelling. Empty football payloads are invalid even when HTTP succeeds.

Understat has no current production xP authority and may not become release-critical without explicit promotion evidence.

### Apex native models — shadow/challenger + decision mechanics

Apex's proprietary forecast surfaces—minutes, attacking rates, team/fixture translation, clean sheets, DEFCON, set-piece/bonus components—remain valuable shadow/challenger models and diagnostics.

Apex remains authoritative for the **decision engine**: FPL legality, current-state finance, optimiser mechanics, XI/captain/vice/bench/autosubs, parity and receding-horizon action selection.

### Historical data — priors/evaluation

Historical datasets support priors, replay and calibration. Historical identity may never overwrite current Official identity. Known outcomes cannot be relabelled as prospective evidence.

### Independent solvers — assurance

Pinned independent solver tooling validates optimisation/mechanics on the same sealed projection surface. Solver parity validates the decision implementation, not the projection forecast.

### Current football evidence — short-lived context

Official club injury updates, manager press conferences/interviews, confirmed transfers and trusted current sources may inform availability, minutes, role, lineups, penalties and set pieces.

Requirements:

- attributable source/URL;
- publication time and freshness/expiry where relevant;
- exact Official player identity attachment;
- no ambiguous surname-only mapping when identity is not uniquely proven;
- no retrieval-time substitution for unknown publication time;
- no ordinal set-piece rank converted into an invented literal share.

Hard adverse evidence may constrain eligibility. Soft evidence affects forecast uncertainty/scenarios rather than manufacturing point bonuses.

## Provenance rules

- Pin governed upstream code/data revisions in `upstreams.lock.json`.
- Record source timestamps, versions and health in generated decision state.
- Keep production authority separate from enrichment/shadow status.
- Never silently substitute a similarly named player.
- Never silently renormalise around missing canonical AIrsenal rows.
- Never treat an optional-enrichment outage as a production blocker unless the active production dependency graph actually requires that source.
- Any source/promotion change must be recorded and tested.

## Prospective forecast ledger

Production and shadow providers should be frozen before each deadline with season, Gameweek, deadline/forecast timestamp, Official snapshot identity, player ID, provider/version, xP and key forecast context. Realised outcomes are joined only after the event.

This ledger is the basis for future provider promotion, rejection or learned ensemble weights. Hand-set weights are not a substitute.

## Web usage policy

Web research is supplementary and current-event focused. Use it to close concrete evidence gaps such as injuries, transfers, manager comments, expected lineups or set-piece changes. Do not browse generic lists and construct a competing Apex squad from articles.

## Personal state

Entry `63984` is the configured production manager state. Public picks reflect published deadline state; unpublished private moves are not visible and require exact manual/current-state evidence if they must supersede the public state.
