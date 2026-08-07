# Using Apex directly from ChatGPT

The repository publishes a compact production snapshot so ChatGPT can answer FPL questions from the current validated engine without needing an always-on server.

## Files ChatGPT should read first

When asked for an Apex recommendation, inspect these repository files in this order:

1. `data/generated/apex_latest.json`
   - current production gate;
   - official snapshot provenance;
   - source health and pinned versions;
   - Haaland / no-Haaland / unrestricted scenarios;
   - current risk report;
   - top ranked player alternatives;
   - personalised FPL entry state when published;
   - transfer plan when a deadline squad is available;
   - independent solver parity when available.
2. `data/generated/apex_latest.md`
   - human-readable explanation of the same run.
3. `data/generated/solver_parity.json`
   - latest direct Apex-vs-open-fpl-solver squad/XI/captain comparison.
4. `data/generated/airsenal.csv`
   - genuine pinned AIrsenal player/Gameweek forecast evidence.
5. `upstreams.lock.json`
   - exact upstream revisions used by the pipeline.

Do not answer from a remembered historical team when these files are available.

## Safety rule

A result is a **full Apex recommendation** only if `apex_latest.json` says both:

```json
{
  "safe_to_act": true,
  "full_apex_ready": true
}
```

If either flag is false or the file is missing/stale, report the blocker and refresh the pipeline instead of presenting an old squad as current.

## Personal FPL entry

The 2026/27 pipeline is configured for FPL entry **63984**.

Before the GW1 deadline the public FPL API does not expose the manager's live draft, so Apex correctly remains in initial-squad mode and builds the best team from scratch.

After each deadline, Apex automatically reads the latest published 15-player squad for entry 63984, bank, captain/vice-captain, transfer/chip history and available free transfers. The decision horizon starts at the next open deadline rather than the already-locked Gameweek.

The repository snapshot includes this under `personal_team` and the current multi-Gameweek recommendation under `transfer_plan`.

Public FPL state is a deadline snapshot. It cannot be assumed to include a transfer the manager has already made privately for the next deadline. Therefore:

- if the user asks **before making transfers**, use the public entry state directly;
- if the user says they have already made a transfer after the latest deadline, use the stated change/manual override rather than silently analysing the older public squad.

The pipeline also reconstructs FPL selling prices from the captured pre-GW1 price universe plus public transfer purchase costs where possible. The team-state report says whether those selling prices are exact or partly approximate.

## Typical prompts

After the published snapshot exists, useful requests become simple:

- `Give me the latest Apex team.`
- `What is my best transfer this week?`
- `Should I roll my free transfer?`
- `Give me the best 3-GW transfer path.`
- `Should I take a -4?`
- `Should I wildcard now or wait?`
- `Compare my current squad with the unrestricted Apex optimum.`
- `Compare the current Haaland and no-Haaland structures.`
- `Why is player X ahead of player Y?`
- `Who should I captain and vice-captain?`
- `What changed since the previous Apex run?`
- `Does the independent solver agree with our team?`

For player-vs-player questions, use the current top-player records, xP horizons, expected minutes, tactical role, role confidence, set-piece shares, source health and risk flags. Avoid choosing solely from raw total xP.

## Freshness cadence

The GitHub automation is designed around:

- FPL Core current-data pin refresh every six hours;
- full personalised Apex refresh/publish every six hours;
- genuine AIrsenal refresh inside production runs;
- independent solver parity on its own validation cadence;
- a dedicated final pre-GW1 run on 21 August 2026 morning;
- manual reruns before a deadline after important press conferences or late injury news.

The latest repository snapshot is therefore the durable interface between the model workers and ChatGPT.
