# Apex V2 production authority root

## Status

This contract governs production publication and answer authority. Engineering success does not itself activate production. Real production remains WITHHELD until the PostgreSQL-backed registries, immutable artifacts, champion generation, evidence and current root have been produced and independently qualified in the target environment.

## One authority chain

The authoritative chain is intentionally acyclic:

`ReleaseRecord -> ArtifactManifest -> ProductionAuthorityRoot`

The `ReleaseRecord` binds one immutable `artifact_manifest_id`. The manifest binds the exact `AUTHORITY_ROOT` and the independent `AUTHORITY_ROOT_REGISTRY_QUALIFICATION`. The root independently closes over champion generation, RuleSet, learning-policy authority, OutcomeTruthRegistry and build provenance. The release does not duplicate a mutable root pointer inside its own semantic identity.

## Mandatory replay

Production never treats an artifact digest as sufficient evidence of semantic type. Before publication and before returning an actionable answer, the manifest is loaded as a typed `ArtifactManifest`; every mandatory role must exist exactly once; member integrity is verified; and mandatory typed objects are replayed through their canonical loaders. Root-linked artifact IDs and semantic IDs must reconcile exactly with the replayed root.

The planning bundle must match season, entry, gameweek and world. The retained reference-solver authorization must be replay-valid for the planning bundle and retained by the mandatory parity claim. Assurance-case, proof-obligation and backend-qualification snapshots must be replayable and, at cutover, must be the exact snapshots supplied to the transaction.

## Independent root registry qualification

The authority-root registry is independently qualified and its qualification artifact is part of the manifest. Production requires the runtime registry backend identity and qualification scope to match that immutable qualification. Filesystem/in-memory mechanism tests do not constitute production qualification. The target production path is the PostgreSQL authority-root registry with persistent shared history and atomic compare-and-swap semantics.

## Current pointer, publication linearization and TOCTOU protection

At validation start the exact season `current_root_id` is captured and must equal the manifest root. There is no synthetic generation counter used as a substitute for authority identity.

For the real PostgreSQL production adapters, release publication is linearized against the current authority root in one database transaction. The cutover transaction locks the season row in `authority_root_pointers` with `SELECT ... FOR UPDATE`, verifies the exact expected root, and compare-and-swaps the release pointer before releasing that root lock. A concurrent root CAS therefore cannot commit between root verification and release-pointer publication: it linearizes before publication and causes cutover to fail, or after publication has committed.

The public cutover also performs a final root-pointer recheck after the publication transaction. A root rotation immediately after a valid publication is not treated as an atomic-publication failure, but it makes the old manifest/root closure non-current; the answer-serving gate therefore withholds it. Reference and mechanism-only non-PostgreSQL registries retain the portable before-CAS and after-transaction root checks, but they are not production qualification evidence.

Answer resolution captures the exact release and root current pointers and re-reads both immediately before returning `CURRENT`. Any change during serving is fail-closed.

## Validity

Root validity is half-open: `[valid_from, valid_until)`. Cutover requires the root to cover the release's complete declared validity horizon, not only the publication instant. Answer resolution replays the root, champion authority and release at the caller's actual `as_of`. A release that was valid when published therefore becomes non-actionable when any required authority expires.

## Publication and serving surfaces

`apex_fpl.control.production_cutover.execute_production_cutover` is the only supported V2 production publication entry point. The historical transaction implementation is private (`_production_cutover_legacy.py`) and exists only to preserve its detailed proof/certificate mechanics beneath the rooted façade and to retain low-level regression coverage. Source tests reject unapproved imports of the private engine.

`apex_fpl.control.production_authority.resolve_production_answer_authority` is the V2 production serving gate. It returns `CURRENT` only after release, manifest, root, champion and backend authority all reconcile at the requested `as_of`; otherwise it returns `UNAVAILABLE` with no actionable bundle.

The existing scheduled `Apex Unified` workflow still seals a transitional filesystem runtime packet through `scripts/stage_runtime_release.py`. That bridge is explicitly V1-compatible and is not V2 production activation. It must not be interpreted as satisfying PostgreSQL root-registry qualification or the rooted V2 cutover contract. Production activation requires an operator/runtime path that loads the qualified PostgreSQL adapters and invokes the public rooted cutover and serving gates.

## Certification and activation

Certification is SHA-specific. A green run for an ancestor commit is not certification for a later head. Engineering certification requires the final frozen SHA to pass the repository's unit, backend-contract, lint, governance and build/provenance checks plus the authority-root adversarial and PostgreSQL atomic-publication tests. The dedicated backend-contract job carries these authority tests explicitly so they fail fast on production-control regressions rather than relying only on the broad suite.

Engineering certification must be reported as **ENGINEERING CERTIFIED / WITHHELD** unless genuine target PostgreSQL evidence, current root, production candidate/champion and publication evidence exist for that same production context. CI success must never fabricate those artifacts, silently weaken qualification, merge the PR, switch a current production pointer, or make an FPL recommendation actionable.
