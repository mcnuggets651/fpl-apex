# FPL Core registration-lag policy — 2026-08-17

## Triggering production evidence

A fresh Adaptive Strategy run on 2026-08-17 built a complete 590-player Official FPL
universe and a complete 590 x 8 canonical projection matrix, but the latest verified
FPL Core pin contained 587 players. The three Official-only IDs were 588, 589 and 590,
which formed a contiguous trailing registration block immediately after Core's maximum
player ID 587.

Pinnacle correctly failed closed under the old unconditional 100% Core-row rule. This
was not missing canonical identity or missing canonical projection coverage: Official
FPL remained authoritative for identity/club/position/price/status and all 4,720
player/Gameweek projection pairs were present. It was an enrichment-source publication
race.

## Production policy

The target for FPL Core official-player coverage remains 100%. The gate may report a
non-blocking `fallback` rather than `pass` only when **all** of these conditions hold:

1. Core coverage is at least 99%;
2. no more than five Official players are missing from Core;
3. every missing Official ID is strictly greater than the maximum player ID present in
   Core, so the gap is append-only rather than an internal data hole; and
4. every missing player has a complete, finite canonical projection surface for every
   requested Gameweek.

The missing Core values remain absent. Apex does not manufacture Core xG/xA, preseason,
DEFCON, historical minutes or other enrichment values for those players. Official FPL
facts and the normal Apex fallback/prior path are used transparently until Core catches
up.

The existing source-health gate remains separate and unchanged. If the pinned Core
source is unavailable or stale, the required source fails regardless of row coverage.

## Failure cases

The fallback does not apply to:

- an internal missing ID at or below Core's current maximum ID;
- a gap larger than five players;
- Core coverage below 99%;
- any missing player without complete canonical Gameweek projections; or
- complete Core-source failure/staleness.

Those conditions remain production blockers.

## Why this does not weaken all-player truth

Player truth still requires 100% Official hard-fact coverage and 100% canonical
player/Gameweek projection coverage. The policy distinguishes a missing enrichment row
from a missing player or missing forecast. It therefore keeps the engine live through a
small upstream registration race without silently dropping players, inventing evidence,
or allowing a broad/structural Core failure to pass.
