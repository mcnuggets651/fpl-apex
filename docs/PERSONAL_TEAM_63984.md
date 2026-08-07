# Personal Apex workflow — FPL entry 63984

Apex is configured to use public FPL entry **63984** as the default manager state for the 2026/27 season.

## Before the GW1 deadline

FPL does not publicly expose another manager's live draft before the deadline. Apex therefore does **not** pretend the entry ID reveals the unpublished GW1 team.

The correct pre-GW1 behaviour is:

1. refresh Official FPL, fixtures, availability, news and preseason evidence;
2. refresh genuine AIrsenal forecasts;
3. build unrestricted, Haaland and no-Haaland optimal squads from scratch;
4. recommend the best final 15, XI, captain, vice-captain and bench.

A dedicated workflow runs this final build on **21 August 2026 at 08:15 UK time**.

## After each deadline

Once a Gameweek deadline has passed, the public entry endpoint exposes that Gameweek's 15-player picks. Apex automatically:

1. identifies the latest published squad for entry 63984;
2. reads bank and team value from the deadline snapshot;
3. replays transfer/chip history to calculate free transfers available for the next deadline;
4. restores the manager's selling-price basis where it can be reconstructed;
5. starts the optimisation horizon at the **next open deadline**, never the already-locked Gameweek;
6. produces the best immediate transfer plus the optimal multi-Gameweek path.

The personalised snapshot is written to:

```text
reports/team_state.json
```

and the transfer strategy is included in:

```text
reports/latest.json
reports/latest.md
```

## Selling prices

Apex captures the official pre-GW1 price universe in its persistent Actions cache. For players bought later, public transfer history provides the purchase cost. This allows the FPL half-profit selling-price rule to be reconstructed for most/all owned players instead of assuming that a player can always be sold for his current market price.

The team-state report records whether selling prices are exact or partly approximate.

## Important public-API limitation

The public entry API is a **deadline snapshot**. It cannot be trusted to reveal private transfers you make after one deadline but before the next.

Therefore the weekly workflow is:

- Ask Apex for the transfer/strategy **before making your move**: no manual input is needed.
- If you already made one or more transfers after the latest deadline, tell Apex what changed (or place an explicit manual override in `data/manual/current_squad.csv` and `team_state.yaml`). Manual state has priority over the public snapshot.

This prevents Apex from silently analysing an old squad.

## Commands

```bash
# Check which team state Apex currently sees
apex-fpl sync-team

# Full personalised 8-GW analysis
apex-fpl run --scenario both --horizon 8 --force

# Personalised transfer path only
apex-fpl plan-transfers --horizon 8 --force
```

## Weekly questions this supports

With the entry connected, normal questions can be answered against the current squad, for example:

- "What is my best transfer this week?"
- "Roll or use my free transfer?"
- "Give me the best 3-GW transfer path."
- "Should I take a -4?"
- "Who should I captain and vice-captain?"
- "Should I wildcard now or wait?"
- "Compare my current structure with the unconstrained Apex optimum."

The recommendation should still be refreshed close to the deadline because injuries, transfers, manager comments and starting-role evidence can change late in the week.
