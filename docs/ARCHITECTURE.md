# Apex FPL Architecture — HISTORICAL PRE-V2

> **HISTORICAL / NON-SERVING DOCUMENT**
>
> This file preserves the original pre-V2 architecture for forensic and legacy-model research context. It is **not** the current production system map and must not be used to determine serving authority.
>
> Current sources:
> - machine authority: `docs/APEX_V2_AUTHORITY.json`;
> - human continuity: `docs/FPL_APEX_MASTER_STATE.md`;
> - capability registry: `docs/APEX_CAPABILITY_REGISTRY.yaml`;
> - current cross-repository system map: `docs/APEX_ARCHITECTURE.md`.
>
> The current V2 authority classifies the old `scripts/run_apex.py`, generated recommendation outputs and pre-V2 selector chain as historical/non-serving.

## Historical decision pipeline

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

Official FPL `bootstrap-static` defined the player universe. Auxiliary rows were joined by FPL player ID. External club, position, price or name fields were diagnostic only and could not override official values.

If official FPL could not be fetched on a live refresh, this architecture failed the run rather than treating stale identity or fixtures as current.

## 2. Source adapters

Historical adapters isolated upstream projects from the old core model:
- `OfficialFPLClient`
- `FPLCoreClient`
- `AIrsenalProjectionAdapter`
- `OddsAdapter`
- RSS/Atom collector

## 3. Integrity and provenance

The historical `reconcile()` path recorded conflicts between canonical and auxiliary fields. Official values won. Source status rows were written to generated reports.

## 4. Feature layer

Historical statistical features included xG/xA rates, minutes, preseason evidence, availability, defensive contributions, set pieces, goalkeeper save rate, fixture strength and optional external expert predictions.

## 5. Expected minutes

The old expected-minutes model blended established/preseason usage and availability separately from xP.

## 6. Fixture-level expected points

The old pipeline projected player/fixture rows and aggregated them to Gameweeks, including DGWs.

## 7. Ensemble and risk

The old `src/apex_fpl` stack used configured expert weights and risk-adjusted projections. **This is not the V2 serving-provider constitution.** Current serving roles come only from `docs/APEX_V2_AUTHORITY.json`.

## 8. Initial squad MILP

The historical optimiser selected squad/XI/captain under budget, formation and club constraints.

## 9. Multi-GW transfer MILP

The historical transfer planner modelled transfer-in/out, free-transfer roll state, hits and bank cash flow.

## 10. Reporting

Historical results were reproduced from generated projections, Official state, configuration, team state, source health and warnings.

The machine-readable generated JSON surfaces from this architecture are retained as historical interfaces. They are **not** the current ChatGPT/manager decision boundary. Current owner questions route through public V2 authority and the approved private query plane described in `docs/APEX_ARCHITECTURE.md` and `docs/CHATGPT_APEX_QUERY_POLICY.md`.
