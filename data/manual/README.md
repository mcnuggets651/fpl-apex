# Manual inputs

Apex is designed to run without private credentials for GW1 squad building. After the season starts, the multi-GW transfer planner needs the exact current squad and transfer state because public FPL picks do not show transfers made for the next deadline before that deadline passes.

## `current_squad.csv`

Create a CSV with exactly 15 unique official FPL player IDs:

```csv
player_id
123
456
...
```

Use official FPL IDs only. Apex will reject a malformed or non-15-player file rather than guess.

## `team_state.yaml`

```yaml
bank: 0.5
free_transfers: 2
```

`bank` is in millions. Free transfers are clamped to the official 1–5 range.

## `availability.csv`

Optional explicit overrides for information you have verified:

```csv
player_id,availability_multiplier,confidence,reason
123,0.2,0.95,official club says ruled out
```

The multiplier changes expected minutes. The official FPL status/chance remains part of the calculation, so this is an additional evidence layer rather than an identity override.

## `player_context.csv`
Optional verified context keyed by official FPL `player_id`. Copy `player_context.example.csv` to `player_context.csv`. It supports tactical role, role attack/assist multipliers, start probability, expected-minutes override, rotation/injury/transfer risk, penalty share, set-piece share, manager confidence, reason, source URL and timestamp. Canonical club/position/price/name fields are forbidden.
