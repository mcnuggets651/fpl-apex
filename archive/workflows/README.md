# Archived workflow manifest — PR #64 architecture freeze

These workflows are intentionally removed from `.github/workflows` so they cannot be mistaken for permanent production/acceptance automation. Their exact YAML is preserved under `archive/workflows/` using the same Git blob content, and every earlier version remains recoverable from Git history.

Archived on 2026-08-16:

- `bootstrap-publish.yml` — legacy bootstrap snapshot publisher; superseded by Apex Unified atomic publication.
- `publish-apex.yml` — legacy snapshot publisher; superseded by Apex Unified.
- `fixture-blend-decision-audit.yml` — one-time fixture-blend promotion audit; the production team-strength gate is now `team-strength-validation.yml` and the validated fallback is frozen in config/evidence.
- `joint-initial-path-audit.yml` — superseded by `joint-path-promotion-audit.yml`, which validates the complete adaptive/receding strategy plus all-player truth and final evidence identity.
- `solver-parity.yml` — standalone parity workflow superseded by parity embedded in Apex Unified and the Adaptive Strategy Audit on the exact sealed surface.
- `understat-player-predictive-audit.yml` — historical signal-promotion audit; current production protection is the bounded Understat Production A/B workflow. Restore this workflow only when a new Understat player-signal challenger is intentionally reopened.

Permanent operational/acceptance workflow surface after the freeze:

- `airsenal.yml` — refresh pinned AIrsenal forecasts.
- `apex.yml` — deterministic repository CI/governance.
- `gw1-final-2026.yml` — one-off 2026/27 GW1 deadline execution; retire after GW1.
- `joint-path-promotion-audit.yml` — final adaptive/receding strategy acceptance.
- `pinnacle.yml` — Apex Unified production workflow.
- `production-readiness.yml` — manual full release acceptance.
- `projection-policy-audit.yml` — bounded projection-policy acceptance.
- `projection-shadow-audit.yml` — projection observability/shadow diagnostics.
- `refresh-core-pin.yml` — immutable FPL Core pin refresh.
- `team-strength-validation.yml` — production team/fixture model validation.
- `understat-player-production-ab.yml` — production Understat player-component regression A/B.

GitHub may continue to display historical workflow registrations/runs in the Actions UI after their YAML is moved. That UI history is not executable production code; the repository tree above is the governed active surface.
