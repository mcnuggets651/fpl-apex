# Apex 2026/27 Champion–Challenger Roster

This file is the operating roster for the prospective model tournament. It is deliberately small. A model being interesting is not enough to create an engineering task.

## Production champion

| Model | Status | Production authority | Notes |
|---|---|---:|---|
| AIrsenal | CHAMPION | Yes | Sole serving xP source until a frozen promotion review approves a replacement. |

## Active challengers

| Model | Status | Production authority | Horizon | Notes |
|---|---|---:|---|---|
| Dastan | ACTIVE_CHALLENGER | No | H1 | Prospective benchmark; currently not horizon-compatible for champion promotion. |
| PITCHSIDE | ACTIVE_CHALLENGER | No | Multi-GW source | Independent public model. Exact FPL-code mapping. Current coverage deficiencies affect promotion eligibility, not its usefulness as a benchmark. |
| Apex Proprietary | ACTIVE_CHALLENGER | No | H1–H8 target | Independent raw Apex xP shadow. Uses hardened minutes, player attacking-rate credibility controls and an independent team-goal/clean-sheet layer. No AIrsenal/blended xP may enter its export. |

## Correlated diagnostic

| Model | Status | Production authority | Notes |
|---|---|---:|---|
| OpenFPL-current | CORRELATED_DIAGNOSTIC | No | May be scored, but Dastan/OpenFPL are one methodological family for consensus/disagreement language. |

## Watchlist — not authorised engineering work

| Model/source | Status | Activation gate |
|---|---|---|
| Daniel Mehta | WATCHLIST | Add only if a continuing pre-deadline machine-readable feed is reliably available with trivial Official-FPL identity mapping. |
| Linus-J | WATCHLIST | Same easy-adapter gate. |
| MattBryantt | WATCHLIST | Same gate; do not create or pay for a new odds/API dependency merely to add this challenger. |

## Fixed rules

- No model voting, averaging, weighting or blending in production.
- Challengers never silently change the champion forecast.
- Every prospective forecast must be sealed before the relevant FPL deadline.
- Tournament promotion rules live in `src/apex/governance/tournament.py` and are not tuned after observing which model is winning.
- A watchlist source becomes active only when integration is genuinely easy, reliable and hindsight-safe.
- The Command Center/app is not part of model development and remains out of scope until the core engine is frozen.
