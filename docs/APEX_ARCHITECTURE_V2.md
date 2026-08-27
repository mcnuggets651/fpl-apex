# Apex V2 Architecture

## Constitutional status

The 23 August 2026 architecture-freeze directive is the governing design contract. V2 is a modular monolith with dependency direction:

`core -> ports <- adapters -> world -> forecast -> decision -> assurance -> control`

Learning is offline and interfaces invoke qualified capabilities. Network access ends at the world seal. Independent/untrusted workers such as AIrsenal, joint-scenario generators and the reference solver execute outside the core runtime dependency graph.

## Change control

A constitutional redesign requires a concrete counterexample, violated invariant, proof that ordinary repair is insufficient, an ADR, a failing reproducer, migration impact and AssuranceCase impact. Otherwise findings are implemented as bugs, experiments, adapters, policies, tests or operations changes.

## Release authority

A release is not authorised by ad-hoc booleans. A machine-readable ProofObligation registry defines mandatory claims. An AssuranceCase links each claim to evidence, tests and artifacts. `ReleaseCertificate` is derived from that case and fails closed on missing, failed or inconclusive mandatory claims.

## Semantic identity

Execution IDs and semantic IDs are separate. Durable semantic content uses the documented restricted canonical JSON profile and SHA-256. Floats cannot silently enter semantic identity; governed numerical values must first pass NumericPolicy quantisation/encoding.

## Scenario robustness

Joint dependence is produced only by an explicitly governed external worker and enters the decision layer as a sealed immutable `ScenarioSet`. Slice 7 marginal scenario labels never establish cross-player correlation. Every compared submitted action is scored unchanged on common nested prefixes with exact FPL realization mechanics. The historical 256-scenario count is a minimum floor rather than a convergence certificate; stability requires governed broader-prefix reconciliation and canonical Forecast xP reconciliation. Nonconvergence remains `INCONCLUSIVE`, exposes no robustness-preferred action, and cannot silently replace the expected-value decision objective. See `docs/APEX_SCENARIO_CONVERGENCE_V2.md`.

## Independent decision assurance

A sealed `DecisionResult` is not publication-authorised solely by certificates produced inside the DecisionEngine. Slice 10 adds two independent release-blocking proofs: a reference mechanics certificate produced without importing `decision.engine` or `decision.mechanics`, and an external reference-solver parity certificate admitted through a qualified worker registry. Missing, limited, errored, unqualified or contradictory independent evidence never becomes PASS by absence. The assurance layer can certify, block or remain inconclusive; it cannot mutate the selected action or introduce new live data. See `docs/APEX_INDEPENDENT_ASSURANCE_V2.md`.

## Durable production control plane

Reference filesystem stores remain local/test infrastructure. Production authority requires the PostgreSQL control plane introduced in PR #85: persisted logical ArtifactStore/ReleaseRegistry identities, immutable content/release history and transactional stale-writer-safe current-pointer CAS. Backend qualification is two-plane: fresh mechanical behavior plus retained production deployment/operations evidence. CI proves implementation mechanics only and cannot impersonate a deployed production database. See `docs/APEX_BACKEND_OPERATIONAL_QUALIFICATION_V2.md`.

## Prospective empirical operations plane

PR #86 adds an operator adapter above the existing pure empirical contracts rather than changing their statistics. The operational path is intentionally fail-closed:

`production PostgreSQL -> immutable candidate -> prospective experiment declaration -> future retained outcome -> replay-derived qualification -> reviewed qualified-candidate proposal -> separate champion admission`

The operator adapter records candidate availability, experiment declaration and result availability at execution time. Those chronology fields are not caller-controlled. It refuses declarations after the evaluation window starts and outcomes before the window ends. Qualification cannot mutate a champion; candidate materialization returns a reviewable registry row only. The `apex-v2` CLI has no filesystem production fallback and never performs cutover. See `docs/APEX_PROSPECTIVE_EMPIRICAL_OPERATIONS_V2.md`.

## Champion authority plane

PR #87 closes the trust gap between `QUALIFIED` and “selected for production”. Qualification does not confer champion authority.

Forecast-model authority reuses the existing immutable learning chain: a retained `ModelPromotionCertificate` with decision `PROMOTE` must be the exact source of the `ModelRegistryGeneration` that names the forecast champion. DecisionPolicy, scenario-generator and scenario-policy candidates require their own exact typed empirical qualification plus a separate immutable reviewed `ChampionAdmissionCertificate`.

Those four authorities are composed into one parent-linked `ProductionChampionGeneration`. Generation transitions are stale-writer-safe and retain review/change-control evidence. Runtime publication code is verifier-only: it replays the generation and exact-matches the forecast model, DecisionPolicy, `ScenarioSet.scenario_generator_id` and `RobustnessReport.scenario_policy_id` in the already replayed production planning bundle. Runtime code cannot issue admissions or create generations.

Production publication authorization schema v2 binds the exact champion-generation artifact. A missing generation may be retained only on a WITHHELD attempt; authorization cannot become actionable without one. Answer authority independently replays the same generation against the bundle again before exposing a current recommendation. See `docs/APEX_CHAMPION_AUTHORITY_V2.md`.

## Production boundary

A green implementation branch, green CI database, SHADOW candidate, SUPPORTED certificate, QUALIFIED candidate or synthetic champion generation is not independently sufficient for publication. Production requires genuine reviewed champion authority, exact qualified deployed backend identities, a replay-valid schema-v2 planning bundle, complete AssuranceCase, exact reference-solver authority, publication authorization and atomic PUBLISHED release. Until that chain exists, V2 remains WITHHELD.
