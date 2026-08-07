# Apex FPL Architecture

## Decision pipeline

```text
Official FPL API
      |
      v
Canonical player/team/fixture universe
      |
      +---- FPL Core statistics + preseason
      +---- optional AIrsenal projections
      +---- official/manual/news availability
      +---- optional market prior
      |
      v
Integrity + feature layer
      |
      v
Expected minutes -> fixture-level xP -> expert ensemble -> uncertainty/risk
      |
      +---- Initial 15-player MILP
      |
      +---- Multi-GW transfer MILP
      |
      v
Auditable report + source health + scenario comparison
```

## 1. Canonical entity layer

The official FPL `bootstrap-static` response defines the player universe. Auxiliary rows are joined by FPL player ID. External club, position, price or name fields are diagnostic only and cannot override the official values.

If official FPL cannot be fetched on a live refresh, Apex fails the run. An old “confident” squad is less useful than a clear failure when identity or fixtures might have changed.

## 2. Source adapters

Adapters isolate upstream projects from the core model:
- `OfficialFPLClient`
- `FPLCoreClient`
- `AIrsenalProjectionAdapter`
- `OddsAdapter`
- RSS/Atom collector

This avoids copying large upstream repositories into Apex and makes it possible to upgrade or remove one source without rewriting the optimisation layer.

## 3. Integrity and provenance

`reconcile()` records conflicts between canonical fields and auxiliary fields. The official value wins. Each source also produces a `SourceStatus` row with success/failure details and timestamp, written to `reports/sources.csv`.

## 4. Feature layer

Statistical features include:
- xG/90, xA/90 and goal involvement;
- starts/minutes;
- preseason starts/minutes/xG/xA;
- official player status and chance of playing;
- defensive contributions;
- set-piece/penalty order;
- goalkeeper save rate;
- fixture attack/defence strength;
- optional external expert predictions.

## 5. Expected minutes

The expected-minutes model blends established usage and preseason usage, then applies official availability. Manual verified evidence and conservative news signals can reduce it further. It is bounded to 0–90.

This model is deliberately separate from xP so rotation/news improvements can be calibrated independently.

## 6. Fixture-level expected points

Apex projects each player once per actual fixture. Therefore:
- no fixture => zero xP;
- two fixtures in one Gameweek => two rows that sum to a DGW total.

The transparent expected-points decomposition includes appearance, attack, clean sheet, defensive contribution, goalkeeper saves, capped bonus prior and set-piece context.

## 7. Ensemble and risk

Expert weights are configured in `config/apex.yaml`. For every player/Gameweek row, only available experts contribute and their weights are re-normalised. This is important early in the season when some upstream models may not yet publish 2026/27 projections.

Apex stores both the mean projection and a risk-adjusted projection. Optimisation uses the risk-adjusted value by default.

## 8. Initial squad MILP

Binary variables represent squad, XI and captain. Constraints enforce budget, 15-man composition, legal XI formation and club limits. Lock/ban constraints create explicit alternative scenarios such as Haaland vs no-Haaland.

## 9. Multi-GW transfer MILP

For every player and Gameweek, binary variables represent squad, XI, captain, transfer-in and transfer-out. Additional state/action variables model the exact 1–5 free-transfer roll state and transfer-hit cost. A continuous bank variable enforces cash flow at current snapshot prices.

This is materially stronger than independently selecting the best squad every Gameweek because it prices the path required to move between squads.

## 10. Reporting

Every result is reproducible from:
- projection rows;
- official current player data;
- model configuration;
- current squad/team state if transfer planning;
- source health;
- integrity warnings.

The machine-readable JSON is intended to be the stable interface for a future dashboard, API or ChatGPT-connected reporting layer.
