# Apex V2 Provider Publication Boundary

This document is a cutover acceptance contract for third-party forecast-provider artifacts.

## Public contract

Apex may publish the selected **canonical Apex serving forecast** in `canonical_forecast.json` because that is the production projection surface consumed by the product and audited against the sealed Official FPL snapshot.

The compatibility asset `provider_forecasts.tar.gz` is **provenance-only**. Each provider member may contain provider identity/version, generation time, season/scoring contract, supported horizons/runtime dependencies, and the SHA-256/byte identity of the corresponding frozen provider surface.

It must never contain:

- provider forecast rows;
- `expected_points` or equivalent raw xP exports;
- a copy of upstream provider player-level output;
- private manager state, decisions, credentials, or other private/sensitive data.

The frozen full provider surfaces are bound to the public provenance entries by exact SHA-256 and byte length. They are never republished as public provider exports.

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

Before V2 cutover, both unit/privacy rehearsal and a real exact-head production rehearsal must prove that:

1. public `provider_forecasts.tar.gz` contains provenance entries only;
2. every public provenance entry binds to a valid 64-hex SHA-256 identity and byte length for its frozen provider surface;
3. no public archive member contains `rows`, `expected_points`, or raw provider player-level projections;
4. `canonical_forecast.json` remains the only public player-level serving forecast surface;
5. the public Release retains the explicit six-asset allowlist and contains no private-manager state;
6. authenticated production persists the separate immutable two-asset private evaluation Release before the public final Release;
7. the private evaluation archive verifies byte-for-byte against the public pre-deadline commitments; and
8. post-GW evaluation refuses regeneration and computes metrics only from those verified private frozen surfaces.

Any regression violates the provider publication/evaluation contract and blocks production publication/cutover.
