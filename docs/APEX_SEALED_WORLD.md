# Apex V2 Sealed Global World

Slice 2 separates acquisition from computation.

## Contract

One acquisition boundary may perform network I/O. Every HTTP response used to build the official global world is retained byte-for-byte in `ArtifactStore` and receives:

- source identity;
- request method, URL and parameters;
- retrieval timestamp supplied by an injected clock;
- freshness policy metadata;
- selected response provenance headers;
- raw byte size;
- SHA-256 content identity;
- a `RawCaptureId` and immutable capture-manifest artifact.

The manager-neutral `GlobalWorld` is then identified only by governed schema/season, immutable source artifact identities and validated world counts. `RunId`, retrieval timestamp, local path, FPL entry ID and manager state do **not** enter `GlobalWorldId`.

## Seal rule

After `GlobalWorld` is sealed, consumers replay it with `load_official_global_world(manifest_artifact_id, store=...)`. That API deliberately accepts no HTTP transport. A `SealedTransport` sentinel exists for negative tests and raises on every request.

The old `run_pipeline()` retrieval path remains V1 compatibility code during migration. It is not the V2 world authority and will be removed only after downstream V2 consumers have moved to the sealed-world contract.

## Current Slice 2 source scope

The first vertical slice seals the two Official FPL manager-neutral identity surfaces:

1. `bootstrap-static/` — players, clubs, positions, official prices, availability fields and Gameweek metadata;
2. `fixtures/` — canonical fixture identity and scheduling surface.

Additional global enrichments can be added as independently typed captures without weakening the rule that Official FPL remains canonical for player identity, club, position, price, availability and fixtures.
