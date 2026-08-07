# Using Apex directly from ChatGPT

The repository now publishes a compact production snapshot specifically so ChatGPT can answer FPL questions from the current validated engine without needing access to GitHub Actions artifacts or an always-on server.

## Files ChatGPT should read first

When asked for an Apex recommendation, inspect these repository files in this order:

1. `data/generated/apex_latest.json`
   - current production gate;
   - official snapshot provenance;
   - source health and pinned versions;
   - Haaland / no-Haaland / unrestricted scenarios;
   - current risk report;
   - top ranked player alternatives;
   - transfer plan when a current squad is configured;
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

## Typical prompts

After the published snapshot exists, useful requests become simple:

- `Give me the latest Apex team.`
- `Compare the current Haaland and no-Haaland structures.`
- `Why is player X ahead of player Y?`
- `What are the highest-risk picks in the Apex squad?`
- `Show me the captain and vice-captain confidence.`
- `What changed since the previous Apex run?`
- `Which player is the best £6.0m midfielder alternative?`
- `How much xP do I lose by forcing Haaland?`
- `Does the independent solver agree with our team?`

For player-vs-player questions, use the current top-player records, xP horizons, expected minutes, tactical role, role confidence, set-piece shares, source health and risk flags. Avoid choosing solely from raw total xP.

## Current-squad transfer advice

To unlock personalised transfer paths after the season starts, add the real 15 official FPL IDs to the private/local `data/manual/current_squad.csv` and bank/free-transfer state to `data/manual/team_state.yaml` in the execution environment. These files are gitignored intentionally.

Until that explicit team state is supplied, Apex should be described as an initial-squad / wildcard-structure optimiser rather than pretending it knows the user's unrevealed transfers.

## Freshness cadence

The GitHub automation is designed around:

- FPL Core current-data pin refresh every six hours;
- full Apex publish every six hours;
- genuine AIrsenal refresh daily;
- independent solver parity daily;
- manual reruns before a deadline after important press conferences or late injury news.

The latest repository snapshot therefore becomes the durable interface between the model workers and ChatGPT.
