# Archived workflow manifest

Workflow YAML under this directory is intentionally inert. GitHub Actions executes workflow definitions only from `.github/workflows`, so moving obsolete publishers or diagnostics here preserves forensic source without leaving an alternate executable production or CI path.

Current machine authority: [`../../docs/APEX_V2_AUTHORITY.json`](../../docs/APEX_V2_AUTHORITY.json).

## Apex V2 production boundary

The frozen certified engine is `99cc7b51b0cff45462b567084cb1844cfe0a456f`. The sole serving workflow is `.github/workflows/apex-v2-daily-production.yml`, and **AIrsenal** is the sole serving provider H1–H8. Historical workflows in this directory have no serving authority even when their preserved YAML contains old schedules, `contents: write`, direct pushes, V1 commands, Pinnacle assertions or stale source requirements.

## Archived on 2 September 2026 — V2 authority reconciliation

The following files were moved byte-for-byte from the executable workflow directory:

- `pinnacle.yml` — retired V1/V1.5 Apex Unified/Pinnacle publisher with direct-main publication logic.
- `airsenal.yml` — retired standalone AIrsenal forecast publisher; Apex V2 owns serving AIrsenal acquisition inside the frozen production path.
- `refresh-core-pin.yml` — retired mutable FPL Core pin writer; Apex V2 resolves/freeze-checks accepted source identity during acquisition.
- `gw1-final-2026.yml` — one-off historical 2026/27 GW1 workflow whose date has passed and whose manual dispatch still invoked the V1 runner.

## Archived on 2 September 2026 — final V2 closure

These additional pre-V2 diagnostics were retired after exact-head closure CI proved that their executable contracts were stale relative to the frozen V2 authority model. Each archived file is the exact `main` source that existed before the Node-24 maintenance branch; no forensic content was rewritten during retirement.

- `joint-path-promotion-audit.yml` — Apex Unified/Pinnacle adaptive-strategy audit. Its live failure was caused by the obsolete `fpl_core_playerstats` readiness dependency (0% current official-player coverage and a stale pin), not by the V2 serving engine or the Node-24 action migration.
- `projection-shadow-audit.yml` — pre-V2 same-surface projection diagnostic that called the legacy Unified production safety gate before a diagnostic-only max-EV comparison.
- `understat-player-production-ab.yml` — pre-V2 Understat promotion experiment whose CVaR script treated a normal non-serving research conclusion as a CI failure despite `production_influence=NONE` and `serving_authorized=false`.

Apex V2 Decision Quality and the prospective tournament are the live no-hindsight research/evaluation paths. These archived diagnostics must not be restored to `.github/workflows` without explicit architecture re-certification.

## Earlier archive — 16 August 2026

- `bootstrap-publish.yml` — legacy bootstrap snapshot publisher.
- `publish-apex.yml` — legacy snapshot publisher.
- `fixture-blend-decision-audit.yml` — historical one-time fixture-blend promotion audit.
- `joint-initial-path-audit.yml` — historical initial strategy audit superseded by later research/acceptance work.
- `solver-parity.yml` — historical standalone parity workflow.
- `understat-player-predictive-audit.yml` — historical signal-promotion audit.

All files in this directory are forensic history. Generic governance and the Apex V2 Ops Contract fail if a retired workflow reappears in `.github/workflows`. The Ops Contract permits only the explicit byte-identical retirement migration recorded in PR #117; once that migration is on `main`, subsequent archive modifications fail closed.

GitHub may continue to show historical workflow registrations and run records in the Actions UI after YAML is archived. Those registrations are run history, not executable files in the current repository tree.
