# Apex V2 Deterministic Acceptance Clocks

Apex production freshness and deadline expiry are real-time safety gates. Production code continues to default to the current UTC clock.

Tests, replays and sealed historical validations must not depend on the machine wall clock when they are asserting a specific pre-deadline state. They must inject the intended UTC instant into clock-aware qualification/certification/solve surfaces.

## Contract

- `qualify_surface(..., now=...)` may be pinned by tests/replays; production may omit `now` and uses current UTC time.
- `certify(..., now=...)` may be pinned by tests/replays; production may omit `now` and uses current UTC time.
- `solve_snapshot(..., now=...)` propagates the optional clock into certification; the production CLI omits it and therefore remains real-time.
- No test should remain green or red merely because a hard-coded 2026 deadline or 24-hour freshness window happens to cross the current wall clock.
- Injecting a test clock must never weaken the production stale/expired checks or change their default behavior.

A failure of these invariants is a CI reliability defect and blocks cutover because deadline/freshness tests must remain reproducible after the calendar advances.
