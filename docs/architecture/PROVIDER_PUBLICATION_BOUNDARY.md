# Apex V2 Provider Publication Boundary

This document is a cutover acceptance contract for third-party forecast-provider artifacts and the canonical player-level display surface.

## Public contract

Apex public Releases are **proof/provenance surfaces, not player-level data exports**.

The six-asset public allowlist remains unchanged for compatibility and attestation:

- `public_attempt.json`
- `canonical_forecast.json`
- `provider_forecasts.tar.gz`
- `governance.json`
- `evidence.json`
- `attestation.json`

`canonical_forecast.json` uses `PROJECTION_COMMITMENT_ONLY_V2`. It may publish only the identities needed to verify the sealed production result: season/gameweek, serving provider identities and versions, scoring contract, qualified horizon, Official/canonical SHA-256 identities, private canonical-surface SHA-256, and row/catalog counts.

It must explicitly state:

- `forecast_rows_published: false`
- `official_catalog_published: false`

It must never contain:

- projection rows or expected points;
- player names, prices, statuses, FPL codes or the Official player catalog;
- fixture rows or the Official fixture catalog;
- private manager state or decisions.

The compatibility asset `provider_forecasts.tar.gz` is also **provenance-only**. Each provider member may contain provider identity/version, generation time, season/scoring contract, supported horizons/runtime dependencies, and the SHA-256/byte identity of the corresponding frozen provider surface.

It must never contain:

- provider forecast rows;
- `expected_points` or equivalent raw xP exports;
- a copy of upstream provider player-level output;
- private manager state, decisions, credentials, or other private/sensitive data.

The frozen full provider surfaces are bound to the public provenance entries by exact SHA-256 and byte length. They are never republished as public provider exports.

## Private canonical manager/display surface

Authenticated production embeds the complete canonical serving/display surface inside the existing `private_manager_attempt.json`. The private manager Release remains exactly two assets:

- `private_manager_attempt.json`
- `private_attestation.json`

No third manager asset is introduced.

The private attempt includes:

- `canonical_forecast` — the exact sealed player/fixture/projection surface needed by the owner UI;
- `canonical_forecast_sha256` — SHA-256 of canonical JSON for that surface.

The same digest is committed publicly as `private_canonical_forecast_sha256` in the commitment-only `canonical_forecast.json`. The private attempt ID also binds that digest, and the whole private payload remains covered by `private_attestation.json`.

The Command Center BFF may return the player-level canonical surface only after all of these pass:

1. the public Release is immutable and its public attestation verifies;
2. Cloudflare Access identifies an authorized owner request;
3. the matching private manager Release is immutable and its private attestation verifies;
4. the existing public/private HMAC decision commitment verifies;
5. season, Gameweek, Official snapshot hash and canonical projection hash agree;
6. canonical JSON SHA-256 of the private display surface equals both the private payload digest and the public commitment; and
7. player, fixture and projection-row counts equal the public commitment.

If the latest Release uses the V2 commitment-only contract and those private proofs are unavailable, the BFF fails closed. It does not fall back to reconstructing or downloading a public player-level surface.

Older immutable V1 Releases remain readable for audit/backward compatibility, but they are not the publication contract for new production attempts.

## Private prospective-evaluation contract

Post-Gameweek scoring must evaluate the exact pre-deadline provider surfaces; regenerating a provider after outcomes are known is forbidden. To satisfy that requirement without reopening public redistribution, authenticated production creates a separate immutable private Release before the public final Release:

`apex-v2/private-evaluation/{season}/{run_id}`

Its exact two-asset allowlist is:

- `provider_forecasts.tar.gz` — the byte-exact frozen `providers/*.json` surfaces from the sealed snapshot;
- `provider_attestation.json` — the public-attempt ID, snapshot ID, archive digest, and SHA-256/byte identity for every provider member.

This Release is separate from the two-asset private manager Release. It contains no TeamState, purchase/selling prices, bank, free transfers, chip state, manager decision, commitment key, FPL credential, or private-repository credential.

The public final Release is refused unless both required private Releases have been published immutably. After Official FPL marks the target Gameweek finished, the evaluator may score provider rows only after all of the following verify:

1. the private evaluation Release is immutable and has exactly the two allowed assets;
2. its attestation belongs to the same `public_attempt_id` as the immutable public final Release;
3. the private archive digest matches its private attestation;
4. the private provider member set exactly equals the public provenance member set; and
5. every private member's byte length and SHA-256 exactly match the pre-deadline commitments in the public provenance archive.

An older immutable final Release that predates this private-evaluation contract is not retrospectively regenerated. It is simply ineligible for provider-level prospective scoring under this contract.

## Evaluation credential boundary

The evaluation workflow receives the private GitHub repository/token only so it can read the immutable private provider-evaluation Release. It never receives FPL session cookies or FPL authorization tokens. Evaluation outputs contain Official outcomes and aggregate provider metrics only; raw provider rows remain private. Evaluation can never promote a provider automatically.

## Cutover acceptance

Before V2 cutover, unit/privacy rehearsal and a real exact-head production rehearsal must prove that:

1. public `provider_forecasts.tar.gz` contains provenance entries only;
2. every public provenance entry binds to a valid 64-hex SHA-256 identity and byte length for its frozen provider surface;
3. no public archive member contains `rows`, `expected_points`, or raw provider player-level projections;
4. public `canonical_forecast.json` is commitment-only and contains no player, fixture or projection rows;
5. the full canonical display surface exists only inside the attested private manager payload and hashes exactly to the public commitment;
6. the Access-protected BFF verifies public attestation, private attestation, decision HMAC, identities and canonical-surface hash before returning the private display surface;
7. the public Release retains the explicit six-asset allowlist and contains no private-manager state;
8. authenticated production persists the separate immutable two-asset private evaluation Release before the public final Release;
9. the private evaluation archive verifies byte-for-byte against the public pre-deadline commitments; and
10. post-GW evaluation refuses regeneration and computes metrics only from those verified private frozen surfaces.

Any regression violates the provider publication/evaluation contract and blocks production publication/cutover.
