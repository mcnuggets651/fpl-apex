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


## Tactical roles

Copy `tactical_roles.example.csv` to `tactical_roles.csv` only for roles you have
verified from current tactical evidence. `role_multiplier` is capped to 0.80–1.20 and
defaults to 1.0. Apex does not silently infer a player's current role from an old club,
last season's position, or transfer rumour.

The same file may carry deadline-specific minutes evidence (`expected_minutes_override`,
`start_probability_override`, `appearance_probability_override`) only when the row also
records its evidence type, reason, source URL and update time. Set-piece shares are
explicit 0–1 shares; blank means unknown and must never be interpreted as zero.
