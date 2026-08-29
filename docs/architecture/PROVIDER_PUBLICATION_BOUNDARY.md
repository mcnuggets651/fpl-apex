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

The frozen full provider surfaces remain inside the sealed production snapshot for exact reproducibility and are bound to the public provenance entries by SHA-256. They are not republished as public provider exports.

## Cutover acceptance

Before V2 cutover, both unit/privacy rehearsal and a real exact-head production rehearsal must prove that:

1. `provider_forecasts.tar.gz` contains provenance entries only;
2. every provenance entry binds to a valid 64-hex SHA-256 identity of its frozen provider surface;
3. no archive member contains `rows`, `expected_points`, or raw provider player-level projections;
4. `canonical_forecast.json` remains the only public player-level serving forecast surface;
5. the public Release retains the explicit six-asset allowlist and contains no private-manager state.

Any regression violates the public exposure contract and blocks production publication/cutover.
