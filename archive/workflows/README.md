# Archived workflow manifest — PR #64 architecture freeze

These workflows are intentionally removed from `.github/workflows` so they cannot be mistaken for permanent production/acceptance automation. Their exact YAML is preserved under `archive/workflows/`, and every earlier version remains recoverable from Git history.

Archived on 2026-08-16:

- `bootstrap-publish.yml` — legacy bootstrap snapshot publisher; superseded by Apex Unified atomic publication.
- `publish-apex.yml` — legacy snapshot publisher; superseded by Apex Unified.
- `fixture-blend-decision-audit.yml` — one-time fixture-blend promotion audit.
- `joint-initial-path-audit.yml` — superseded by `joint-path-promotion-audit.yml`.
- `solver-parity.yml` — standalone parity workflow superseded by parity embedded in Apex Unified.
- `understat-player-predictive-audit.yml` — historical signal-promotion audit; retained only as research history.

Archived on 2026-08-28:

- `gw1-final-2026.yml` — one-off 2026/27 GW1 deadline executor. GW1 is complete; keeping it active would expose an obsolete manual execution path and pre-GW1 assumptions.

Current governed operational/acceptance workflow surface:

- `airsenal.yml` — refresh pinned AIrsenal forecasts.
- `apex.yml` — deterministic repository CI/governance.
- `joint-path-promotion-audit.yml` — adaptive/receding strategy acceptance.
- `pinnacle.yml` — Apex Unified production workflow.
- `production-readiness.yml` — manual full release acceptance.
- `projection-policy-audit.yml` — bounded projection-policy acceptance.
- `projection-shadow-audit.yml` — projection observability/shadow diagnostics.
- `refresh-core-pin.yml` — validated FPL Core enrichment-pin refresh.
- `team-strength-validation.yml` — team/fixture-model research and validation surface.
- `understat-player-production-ab.yml` — bounded Understat player-component regression A/B; Understat remains enrichment/shadow unless separately promoted by prospective evidence.

GitHub may continue to display historical workflow registrations/runs in the Actions UI after their YAML is moved. That UI history is not executable production code; the repository tree above is the governed active surface.
