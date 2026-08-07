# Apex FPL consolidation status — 7 August 2026

## Recovered and merged

The previously tested 59-file Apex engine was recovered from the saved Git bundle and
consolidated with the stronger Milestone-2 reliability layer.

Implemented:
- official FPL validation and immutable checksummed snapshots;
- official-ID-only AIrsenal import with common aliases;
- pinned AIrsenal / FPL Core / open-fpl-solver commits;
- expected-minutes probabilities and confidence;
- tactical-role override contract keyed only by official FPL ID;
- xG/xA/xGI, defensive contribution, bonus/set-piece and fixture modelling;
- expert disagreement, uncertainty interval and risk-adjusted xP;
- 1/3/5/8-GW summaries;
- legal MILP squad, XI, captain, bench and Haaland/no-Haaland scenarios;
- multi-GW transfer/chip planner;
- news and availability layer;
- explicit safe-to-act / full-Apex gate.

## Deliberate production blocker

A diagnostic squad may be produced without all optional workers, but `full_apex_ready`
remains false until the genuine pinned AIrsenal forecast covers the requested gameweeks
and the configured news layer is healthy. Apex never substitutes FPL `ep_next` or fake
forecast values and calls them AIrsenal.
