# Apex V2 RuleSet — 2026/27

Slice 3 replaces remembered/scattered gameplay constants with a versioned, provenance-bound RuleSet.

## Authority policy

Only current official Premier League / Fantasy Premier League sources may establish production gameplay rules. Every rule in `config/rules/2026-2027.yaml` carries:

- a stable rule ID;
- the capability it governs;
- an integer/boolean/string/list/mapping semantic value (never uncontrolled float state);
- one or more official source IDs;
- the effective season;
- the effective date.

`RuleSetId` is a deterministic SHA-256 semantic identity over the complete source and rule manifest. Any rule/source change creates a different RuleSet identity.

## Verified 2026/27 sources

The manifest was re-verified against official Premier League/FPL material on 23 August 2026. It covers the current initial-squad budget and shape, maximum players per club, lineup formation, deadline offset, captain/vice behavior, free-transfer allowance and five-transfer bank, extra-transfer hit, position-preserving transfers, the two-half chip inventory and restrictions, the base scoring table, 2026/27 BPS changes, and the new Gameweek final-lock hour.

The RuleSet defines mechanics; Slice 4 owns the exact state transition engine for free-transfer evolution, chips, purchase bases, selling prices, hits and manager state. Slice 3 therefore does not duplicate or prematurely implement transition state.

## Identity policy

Current-season Official FPL integer player IDs are canonical. `PersonId` is a separate reviewed cross-season identifier. Names are retained only as display/audit witnesses and can never resolve decision-critical identity by themselves. Resolution states are exactly `EXACT`, `CORROBORATED`, `AMBIGUOUS`, and `UNMAPPED`; the latter two fail closed for decision-critical use.

The PR #66 identity work was used only as archaeology/regression evidence. Its exact-integer and conflict-detection lessons are retained, while name fallback is deliberately not ported into the V2 authority path.
