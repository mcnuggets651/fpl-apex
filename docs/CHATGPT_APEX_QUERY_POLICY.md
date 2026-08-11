# ChatGPT Apex Query Policy

Authority: [`APEX_OPERATING_MANUAL.md`](APEX_OPERATING_MANUAL.md). This file is a
compact policy summary and cannot override the operating manual.

This policy governs every ChatGPT answer about FPL players, squads, transfers, captaincy, chips, fixtures, expected minutes, expected points, or Apex recommendations.

## Mandatory source order

1. Read `docs/CURRENT_STATE.md` and the Project Brain first.
2. Read `data/generated/apex_answer_context.json`; do not produce an Apex-labelled
   answer from any other artifact.
3. Use the latest committed Apex diagnostics and pinned upstream evidence to explain the canonical result.
4. Keep production, shadow, open-PR and stale artifacts explicitly separated by date/ref.
5. Do not use external web research unless the repository evidence has a concrete gap that prevents a defensible answer.
6. If external research is required, state the missing repo evidence first, use the external source only to fill that gap, and never let it silently replace canonical Apex evidence.

## Player-comparison rule

For comparisons such as Foden vs Semenyo, do not compare headline opinions or isolated projections. Inspect, where available:

- current Official FPL identity, price and status;
- current and prior playing-time evidence;
- preseason starts/minutes and attacking evidence;
- tactical/verified role evidence;
- news audit evidence;
- expected minutes/start/appearance probabilities;
- canonical xP and projection decomposition;
- scenario/CVaR/regret diagnostics;
- whole-squad budget opportunity cost.

If two artifacts were generated from different snapshots or model versions, do not combine their numbers as if they came from one run. Label any older evidence as stale diagnostic evidence.

## Failure rule

If the latest committed artifacts cannot answer the question, say exactly what is missing. Do not invent a probability, role assumption or value judgement and do not browse by default to make the answer look complete.

## Canonical wording

Use `Apex production verdict` only for evidence produced by the current production path. Use `shadow`, `open PR`, `stale diagnostic`, or `external gap-fill` for everything else.
