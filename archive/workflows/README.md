# Archived workflow manifest

Workflow YAML under this directory is intentionally inert. GitHub Actions executes workflow definitions only from `.github/workflows`, so moving obsolete publishers here preserves forensic source without leaving an alternate executable production path.

Current machine authority: [`../../docs/APEX_V2_AUTHORITY.json`](../../docs/APEX_V2_AUTHORITY.json).

## Apex V2 production boundary

The frozen certified engine is `99cc7b51b0cff45462b567084cb1844cfe0a456f`. The sole serving workflow is `.github/workflows/apex-v2-daily-production.yml`, and **AIrsenal** is the sole serving provider H1–H8. Historical workflows in this directory have no serving authority even when their preserved YAML contains old schedules, `contents: write`, direct pushes or V1 commands.

## Archived on 2 September 2026 — V2 authority reconciliation

The following files were moved byte-for-byte from the executable workflow directory:

- `pinnacle.yml` — retired V1/V1.5 Apex Unified/Pinnacle publisher with direct-main publication logic.
- `airsenal.yml` — retired standalone AIrsenal forecast publisher; Apex V2 owns serving AIrsenal acquisition inside the frozen production path.
- `refresh-core-pin.yml` — retired mutable FPL Core pin writer; Apex V2 resolves/freeze-checks accepted source identity during acquisition.
- `gw1-final-2026.yml` — one-off historical 2026/27 GW1 workflow whose date has passed and whose manual dispatch still invoked the V1 runner.

These files must not be restored to `.github/workflows` without an explicit architecture re-certification. Generic governance and the Apex V2 Ops Contract fail if they reappear there.

## Earlier archive — 16 August 2026

- `bootstrap-publish.yml` — legacy bootstrap snapshot publisher.
- `publish-apex.yml` — legacy snapshot publisher.
- `fixture-blend-decision-audit.yml` — historical one-time fixture-blend promotion audit.
- `joint-initial-path-audit.yml` — historical initial strategy audit superseded by later research/acceptance work.
- `solver-parity.yml` — historical standalone parity workflow.
- `understat-player-predictive-audit.yml` — historical signal-promotion audit.

GitHub may continue to show historical workflow registrations and run records in the Actions UI after YAML is archived. Those registrations are run history, not executable files in the current repository tree.
