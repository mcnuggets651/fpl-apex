# All-player truth and set-piece integrity scope

## Problem

Apex currently converts Official FPL ordinal set-piece order into literal shares (`1 -> 1.00`, `2 -> 0.45`, `3 -> 0.15`) and adds those values directly to player xP. An ordinal rank is evidence of hierarchy, not evidence that the player will take a stated percentage of future set pieces. The Schade/Thiago case exposed the semantic error: Official FPL lists Schade second in Brentford's penalty order while its own Scout note says Thiago resumed taking spot-kicks after Schade's miss.

This is a global player-data integrity defect, not a player-specific tuning issue.

## Production correction

1. Official FPL remains canonical for player identity, club, FPL position, price, availability status, fixtures and ordinal set-piece order.
2. Ordinal set-piece order is retained as an observed/canonical rank and must never be converted into a literal probability/share by an unvalidated lookup table.
3. Additive set-piece xP may use an explicit share only when a current, attributable trusted-source override provides that model input. Missing share evidence remains unknown/zero additive adjustment rather than fabricated precision.
4. Historical xG/xA remain the baseline attacking-rate evidence. A separate rank-derived set-piece challenger may be researched later, but it cannot re-enter production without historical predictive and decision-level validation, including a double-counting audit against xG/xA.
5. The all-player truth audit must cover every current Official FPL player and distinguish canonical/observed facts, sourced current overrides, statistical inference and forecasts.
6. Hard factual fields must be complete for 100% of the Official FPL player universe. Unknown future quantities (minutes, next XI, future role) must remain labelled forecasts with confidence rather than being represented as facts.
7. Any explicit set-piece share reaching production without verified provenance is a readiness blocker.

## AIrsenal boundary

AIrsenal remains an independent projection expert. Apex's current adapter imports player/Gameweek expected points (plus optional xMins/confidence), not AIrsenal's complete internal database. AIrsenal agreement on a player's xP therefore does not validate Apex's factual role or set-piece assumptions.

## Acceptance

- `order=2` does not become `share=0.45` (or any other literal share) without explicit sourced evidence.
- set-piece order and set-piece share are separate fields with separate provenance.
- 100% of current Official FPL players pass hard-fact completeness and unique-ID checks.
- every player receives an auditable truth row classifying role/minutes/set-piece inputs as fact, sourced override, inference or forecast.
- an unsourced explicit share fails readiness.
- Schade no longer receives a 45% penalty share solely because he is second in the Official FPL penalty order.
- the full canonical team is re-solved on the corrected surface before any production promotion.
