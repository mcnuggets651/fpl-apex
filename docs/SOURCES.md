# Source hierarchy and contracts

## Tier 1 — canonical identity

### Official Fantasy Premier League API
Used for the live player universe, player IDs, club, FPL position, price, official availability fields, teams, fixtures and Gameweek state. If this source is unavailable, Apex fails the live run rather than silently recommending from stale identity data.

Endpoints used:
- `https://fantasy.premierleague.com/api/bootstrap-static/`
- `https://fantasy.premierleague.com/api/fixtures/`

## Tier 2 — statistical enrichment

### FPL Core Insights
Apex consumes the open 2026/27 CSV outputs, notably `playerstats.csv` and preseason `By Tournament/Friendlies/GW0/playermatchstats.csv`. It provides underlying performance, defensive-contribution and preseason context. It never gets permission to overwrite canonical club/position/price.

Upstream: `olbauday/FPL-Core-Insights`

### AIrsenal
AIrsenal is an independent projection expert. Apex intentionally does not vendor or fork its internals. When AIrsenal has a valid current-season projection export, set `AIRSENAL_PROJECTIONS_CSV`; the ensemble automatically consumes it. If AIrsenal has not yet migrated to the live season, Apex records it as absent and re-normalises the other expert weights instead of fabricating an AIrsenal number.

Upstream: `alan-turing-institute/AIrsenal`

## Tier 3 — availability and market priors

### News
Configured RSS/Atom feeds are title-matched to players and scored conservatively for obvious injury/return language. Every match is written to `news_audit.csv`. This is advisory and cannot change identity.

### Odds
An optional adapter accepts `player_id, market_xp` from a configured endpoint. This is an explicit contract because different commercial bookmakers/odds APIs expose different markets and licences. No unsupported scraping is hidden inside Apex.

## Provenance
Every live run writes `reports/sources.csv`, including whether each source succeeded, row/headline counts and a timestamp. Auxiliary failure degrades gracefully; official FPL failure stops the run.
