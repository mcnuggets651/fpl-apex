# Apex V2 acquisition output contract

## Purpose

Apex V2 acquisition is allowed to execute isolated provider workers that write human-readable or structured status messages to stdout. Those messages are useful in runner logs, but stdout is **not** a stable machine-to-machine protocol.

The production workflow therefore uses a dedicated, atomic snapshot handoff file. This contract prevents provider logging from corrupting GitHub Actions step outputs and makes the acquisition/freeze boundary independently verifiable.

## Production #40 incident class

Production run `33312221205` failed in job `99259228226` at the `Re-anchor Official truth and freeze all inputs once` step. The affected workflow captured the complete stdout of `apex-v2 acquire` into a shell variable and then wrote that value directly to `$GITHUB_OUTPUT`.

An enabled shadow-provider worker can emit its own stdout before `apex-v2 acquire` prints the frozen snapshot path. That makes the captured value multiline. A multiline value written using the single-line `name=value` GitHub Actions output syntax is not a valid machine handoff and can fail the workflow after acquisition itself has already completed.

This failure class is particularly dangerous because it occurs outside the staged acquisition exception path: acquisition may have frozen a valid snapshot, yet no `AcquisitionStageError` diagnostic is produced because the failure belongs to the shell/GitHub-output boundary rather than to an acquisition stage.

## Canonical handoff

`apex-v2 acquire` accepts:

```text
--snapshot-output <path>
```

On successful acquisition it atomically writes exactly one UTF-8 line:

```text
<snapshot-root>\n
```

The CLI may continue to print provider status and the final snapshot path to stdout for human observability. Workflow code must never parse or capture stdout to obtain the snapshot path.

The production and diagnostic workflows must:

1. Allocate a run-local file under `$RUNNER_TEMP`.
2. Remove any stale file before acquisition.
3. Pass the file using `--snapshot-output`.
4. Require the file to exist and be non-empty.
5. Require exactly one line.
6. Require the referenced snapshot directory to exist.
7. Require `<snapshot>/manifest.json` to exist and be non-empty.
8. Only then publish the validated path to `$GITHUB_OUTPUT` using a single-line `printf`.

This makes stdout a log channel only and the snapshot-output file the sole machine handoff.

## Fatal acquisition diagnostics

The canonical public-safe failure record is:

```text
artifacts/v2/diagnostics/acquisition_failure.json
```

`AcquisitionStageError` retains its explicit stage, cause type and stage-controlled message.

Failures that escape the staged acquisition wrapper are also recorded before the CLI exits:

- `runtime_import` — the acquisition runtime could not be imported.
- `acquire_unclassified` — an unexpected exception escaped `acquire_and_freeze`.

For these unclassified paths, arbitrary exception text is intentionally omitted from the uploaded diagnostic because it can contain credentials, cookies, authorization headers, provider payloads or other private material. The exception type and stable failure stage are preserved in the public-safe artifact; private exception detail remains confined to the authenticated runner log.

A failed acquisition must never create the snapshot handoff file.

## Regression guarantees

`tests/test_v2_acquire_output_contract.py` locks the contract by proving that:

- provider stdout noise does not change the one-line snapshot handoff;
- an unclassified fatal exception produces a sanitized diagnostic and no snapshot handoff;
- both production and non-publishing diagnostic jobs use `--snapshot-output`;
- the old `SNAPSHOT="$(apex-v2 acquire ...)"` pattern cannot return;
- both workflows validate the handoff file and frozen snapshot manifest before exporting a GitHub step output.

`tests/test_v2_acquisition_diagnostics.py` continues to lock the normal staged-failure diagnostic contract.

## Architecture impact

This repair changes **only the acquisition/workflow I/O boundary and failure observability**. It does not change:

- the AIrsenal production champion;
- challenger serving authorization;
- provider forecasts or weights;
- optimizer behavior;
- FPL mechanics;
- transfer strategy;
- captaincy logic;
- DEFCON modelling;
- tournament promotion/disagreement policy;
- authenticated manager-state semantics;
- private/public publication policy.

The permanent invariant is simple:

> Human logs may be noisy. Machine handoffs must be explicit, atomic, validated and single-purpose.
