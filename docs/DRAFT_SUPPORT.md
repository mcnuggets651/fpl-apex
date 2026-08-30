# FPL Draft support

Apex supports FPL Draft as a **read-only decision-support surface**. It does not create a second canonical team and it does not modify the Classic-FPL production optimiser, xP objective, safety gate, or answer contract.

## Identity

Configure:

```yaml
fpl_draft_league_id: 12345
fpl_draft_entry_name: "mcnuggets"
```

or use environment variables:

```bash
FPL_DRAFT_LEAGUE_ID=12345
FPL_DRAFT_ENTRY_NAME=mcnuggets
```

The Draft league ID is the numeric value used by the official endpoint:

```text
https://draft.premierleague.com/api/league/{league_id}/details
```

The generic `https://draft.premierleague.com/en/` homepage URL does **not** contain the league ID. If needed, open the Draft league page while logged in and inspect the browser Network requests for `/api/league/<number>/details`; that number is the league ID. League-admin settings may also expose the ID in the page URL.

## Live pool

Run:

```bash
apex-fpl draft-pool
```

This reads only official FPL Draft endpoints:

- `/api/league/{league_id}/details`
- `/api/league/{league_id}/element-status`
- `/api/bootstrap-static`

and writes:

- `reports/draft_pool.csv`
- `reports/draft_pool.json`

The materialized pool contains every Draft player with `available`, `owned`, or `locked` status and, where applicable, the owning league entry.

## ID namespace rule

Draft element IDs are not assumed to equal Classic-FPL element IDs. Any Apex projection join must reconcile player identity through name, club, and position before attaching Classic-FPL/Apex projections. Raw numeric ID equality is forbidden as an identity shortcut.

## Decision rule

Draft recommendations should compare the manager's current player against the **best genuinely available replacement in that league**, not against the global FPL player universe. Scarce premium assets should therefore be evaluated using replacement value / VORP and expected absence length; injury alone is not an automatic drop signal.

The current Command Center already keeps Draft diagnostics subordinate to Classic-FPL production. This integration preserves that separation.
