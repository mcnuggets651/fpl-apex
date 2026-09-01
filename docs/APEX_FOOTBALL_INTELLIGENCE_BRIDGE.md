# Apex Football Intelligence Bridge

Status: **v1 producer contract / SHADOW_RESEARCH_ONLY**

This document defines the one-way information boundary between Apex FPL and Apex Betting. It is intentionally narrower than either system and preserves independent failure domains.

## Repository boundary

Producer: `mcnuggets651/fpl-apex`

Consumer: `mcnuggets651/apex-betting`

Required direction:

```text
FPL Apex production outputs
        |
        | read-only export
        v
apex-football-intelligence-v1 immutable artifact
        |
        | separately validated copy/import
        v
Betting Apex shadow/research adapter
```

Non-negotiable invariants:

- the repositories are not merged;
- Betting Apex never imports Python modules from FPL Apex;
- there is no shared mutable database;
- Betting Apex never writes to FPL Apex;
- neither repository requires the other to be running;
- deleting the exporter leaves FPL production decisions unchanged;
- absence or rejection of the artifact cannot break Betting Apex's separately authorised incumbent path;
- betting prices, edge, CLV, selections, settlement and betting outcomes never feed into the FPL football primitive artifact.

## Audit baseline

The v1 design was audited against FPL Apex `main` at `f90cbd77367575a14c9651d4c2ddde8f577a82ec` and Betting Apex `main` at `ce410c976c56e4eb1c8e797c2cce567455167af4`.

The audit identified mature FPL-native surfaces for:

- expected minutes, start and appearance probability (`models/minutes.py`);
- tactical roles and role confidence;
- availability/news evidence with timestamps and source tiers;
- credibility-adjusted xG/90 and xA/90 (`models/projection.py`);
- defensive-contribution rate and reliability;
- verified set-piece shares;
- official player/team/fixture identity and immutable official snapshots;
- source-health, upstream pins, evidence policy and replay/integrity controls.

The audit also identified a critical leakage boundary: `services/pipeline.py` merges optional `market_xp` before `models/ensemble.py`, and the canonical ensemble can include the configured market expert. Therefore `canonical_ev_xp`, `risk_adjusted_xp`, `projection_confidence` and other post-ensemble values are **not** market-independent football primitives and are excluded from this contract.

## Why v1 reads finished report artifacts

The exporter is deliberately downstream of the normal FPL pipeline. It reads:

- `reports/latest.json`;
- `reports/players.csv`;
- `reports/projections.csv`;
- the exact immutable official snapshot named by `latest.json` (`manifest.json`, `bootstrap-static.json`, `fixtures.json`).

It does not call `run_pipeline`, change `PipelineOutput`, modify optimisation, publish a recommendation, alter captaincy, alter transfer planning, or mutate any production artifact.

This is a stronger isolation property than inserting an exporter into the production workflow: the normal FPL engine has no dependency on the contract module or its output.

## Contract name and versioning

Existing FPL contracts use explicit hyphenated names such as `apex-player-truth-v1` and `apex-fpl-production-snapshot-v2-personalised`. The cross-repository contract therefore follows the same convention:

`apex-football-intelligence-v1`

The machine-readable schema is `contracts/apex-football-intelligence-v1.schema.json`.

A semantic change to an existing field is breaking and requires a new contract version. Adding a field that changes consumer interpretation is also treated as breaking unless both repositories explicitly support the extension.

Betting Apex must declare the exact versions it accepts; it must never accept `v2` by assuming it is compatible with `v1`.

## V1 payload

### Provenance envelope

Every artifact contains:

- schema version;
- `SHADOW_RESEARCH_ONLY` rollout mode;
- `generated_at` / `information_as_of` from the completed FPL report;
- producer repository and exact 40-character commit SHA;
- producer model version;
- deterministic input-lineage identifier;
- official FPL snapshot identity and acquisition timestamps;
- source hashes plus hashes of only the selected primitive columns;
- relevant primitive-source health;
- producer readiness state;
- deterministic payload SHA-256 and artifact ID.

Writes are create-only. An existing output path is never overwritten.

### Player identity

V1 exports producer-local identity only:

- `fpl_player_id`;
- `producer_player_id` (`fpl:<id>`);
- canonical official full name;
- official web name;
- official FPL club ID/name;
- producer team ID (`fpl-team:<id>`);
- FPL position.

`producer_player_id` is **not** a Betting Apex player ID. The consumer must maintain an explicit mapping to its own canonical identity. No fuzzy production match is implied or authorised.

### Fixture identity

Fixtures come from the exact official snapshot, not names/GW inference. Each horizon fixture contains:

- official FPL fixture ID;
- producer fixture ID (`fpl-fixture:<id>`);
- gameweek;
- timezone-aware scheduled kickoff;
- exact official home and away team IDs/names.

Missing kickoff, duplicate fixture identity or a projection that cannot be linked exactly to the official fixture causes export failure.

### Player football primitives

V1 includes:

- expected minutes;
- start probability;
- appearance probability;
- 60+ minute probability;
- minutes confidence;
- availability probability/status;
- tactical role, source and confidence;
- club-change/current-role-evidence state;
- credibility-adjusted Apex-native xG/90 and xA/90;
- attacking-rate reliability and credibility-adjustment flags;
- defensive-contribution/90 and reliability;
- verified set-piece shares when present;
- abstract availability/news evidence state with timestamps/source tier and a SHA-256 locator rather than raw article text/URL.

## Explicit exclusions

V1 does **not** export:

- FPL expected points (`apex_xp`, `xp`, `canonical_ev_xp`, `risk_adjusted_xp`);
- ensemble confidence/disagreement;
- AIrsenal values;
- market odds or `market_xp`;
- FPL price, ownership or transfer signals;
- optimiser selections, squad state, captaincy or transfer plans;
- betting probabilities, edge, CLV, staking, outcomes or settlement;
- raw news/article text;
- raw upstream datasets.

The exporter hashes only whitelisted primitive columns. Consequently even the provenance bytes are unchanged when excluded market/ensemble values change.

## Why team-goal and shot/SOT primitives are not in v1

FPL Apex has a strong `team_goals.py` surface and preseason shooting evidence, but the current finished-report boundary does not persist every active team-goal fallback with an unambiguous run-level provenance manifest. `team_goal_surface.csv` can also remain from a prior run when a later run does not materialise a non-empty Understat surface. Auto-discovering that file would create a stale-file hazard.

Similarly, v1 does not pretend preseason shots/90 or shots-on-target/90 are mature all-context player prop rates.

Therefore the smallest safe contract marks:

- `team_goal_surface=false`;
- `shot_rate90=false`;
- `shot_on_target_rate90=false`.

A later producer contract may add these only after the corresponding surface is materialised atomically with run-level timestamp/hash/source provenance and its semantics are stable enough for a betting consumer.

## Source and licensing governance

The FPL Apex code is MIT licensed. That license does **not** relicense third-party source data.

V1 therefore adopts a conservative data boundary:

- artifact scope is `internal_private_research_only`;
- no raw third-party dataset is embedded;
- no raw article/news text is embedded;
- source URLs are represented by SHA-256 locators in player evidence state;
- only derived numeric model primitives, official identity, timestamps, source-health metadata and provenance hashes cross the boundary;
- the artifact explicitly records `upstream_data_rights_not_relicensed=true`.

Before any broader publication/distribution of produced artifacts, source-specific rights must be reviewed separately. A private Betting Apex research copy is not permission to republish upstream data.

## Freshness and fail-closed producer validation

The producer refuses export for:

- stale report age beyond the configured maximum;
- future-dated report/source/player evidence;
- report/snapshot manifest disagreement;
- corrupted/missing JSON or CSV inputs;
- duplicate official/player/fixture identities;
- player universe mismatch;
- club/position/name mismatch against Official FPL;
- missing expected-minute/start/appearance fields;
- impossible probabilities/minutes;
- missing attacking/defensive primitive columns;
- fixture/projection mismatch or incomplete fixture coverage;
- fixture-varying values for fields defined as player-level v1 primitives;
- unhealthy/missing Official FPL identity source;
- invalid producer commit identity.

Producer readiness is recorded but not silently converted into consumer authorisation. Shadow research may inspect a not-ready snapshot; future production influence must require the Betting-side readiness policy to pass.

## Consumer identity design (PR 2)

Betting Apex must add a separate immutable mapping layer. Minimum mapping record:

- Betting canonical `player_id`;
- FPL `fpl_player_id` / `producer_player_id`;
- canonical name used for review only;
- Betting team ID and FPL team ID;
- effective-from / effective-to timestamps or season scope;
- mapping source/provenance;
- mapping artifact hash/version.

Names are never production join keys. Team/fixture identity must be exact. An absent or ambiguous mapping is a hard validation failure for that player; no fuzzy fallback is permitted.

## Consumer validation design (PR 2)

Betting Apex will independently implement `apex-football-intelligence-v1` rather than importing FPL code. It must reject at least:

- unsupported/unknown schema;
- payload hash mismatch/tampering;
- stale or future-dated information;
- wrong producer repository;
- unsupported producer model version;
- missing provenance/hash fields;
- competition/season mismatch;
- fixture mismatch/horizon mismatch;
- duplicate players/fixtures;
- invalid probabilities/minutes/rates;
- missing critical minutes/start/appearance values;
- identity ambiguity or club mismatch;
- producer readiness failure where the consuming policy requires readiness;
- malformed/corrupted artifacts.

Absence of an artifact is not a reason to invent substitute FPL-derived values. Betting Apex may use only a separately authorised incumbent model or return unavailable/NO BET according to its own governance.

## Shadow evaluation design (PR 3)

The first Betting integration is strictly research-only and compares three fixed surfaces:

A. incumbent Betting Apex;

B. incumbent Betting Apex plus imported football intelligence challenger;

C. market benchmark.

The challenger must be preregistered before prospective outcomes are observed. Required reporting includes, where applicable:

- log loss;
- Brier score;
- calibration intercept/slope and probability buckets;
- market-relative forecast skill;
- CLV under the existing execution/closing evidence contracts;
- edge stability;
- sample size and uncertainty;
- robustness by market and information horizon;
- ROI only as secondary evidence where governed.

No method may be chosen after observing which variant made more profit. The imported signal receives no production weight merely because FPL Apex is sophisticated.

## Promotion design (PR 4)

Production influence requires a separate evidence-bound promotion. The incumbent remains NO BET/current authorised model until the challenger earns promotion prospectively.

Promotion is scoped by market. Match-odds evidence never auto-certifies player props. A shots model never auto-certifies SOT. Every new player market starts with NO BET and its own data, calibration, prospective evaluation and certification path.

## Later player-market work

Only after upstream primitives prove useful should Betting Apex add separately governed models for goals, assists, shots, SOT, fouls, cards, tackles or other markets. Those models should combine opportunity (minutes/start), role/rates, opponent/team context, game-state uncertainty and market-specific settlement rules.

Bet builders come after individual markets. Joint builder probability must emerge from coherent simulated match states, not naive multiplication of marginal probabilities.

A future fragility diagnostic should penalise unnecessary legs, binary low-minute player events, threshold sensitivity, concentrated match-state paths and high primitive uncertainty. Apex must be allowed to answer `NO BET` at a requested multiplier.

## Operator command

The exporter is intentionally standalone:

```bash
python scripts/export_football_intelligence.py \
  --report-dir reports \
  --snapshot-root data/snapshots \
  --producer-commit-sha "$(git rev-parse HEAD)" \
  --season 2026/27 \
  --output /private/path/apex-football-intelligence-v1.json
```

Do not commit produced football-intelligence artifacts to the public FPL repository. Transfer/copy into Betting Apex research storage only through the governed consumer ingestion step.
