# Apex V2 Exact Manager State Contract

## Purpose

An in-season FPL action is financially meaningful only relative to the manager's real permanent squad and exact account state. V2 therefore treats `ManagerState` as decision-critical sealed input rather than a convenience dataframe.

`GlobalWorld` remains manager-neutral. `ManagerState` is combined with it later to form a decision world.

## Currentness states

A structurally complete state has one explicit scope:

- `CURRENT_EXACT` — may enter a live in-season decision after RuleSet validation;
- `DEADLINE_SNAPSHOT` — exact as of a public deadline snapshot, but not proof that no private transfers have happened since;
- `REPLAY_EXACT` — exact historical state for replay, not live authority.

Only `CURRENT_EXACT` is live decision-safe.

A public FPL picks endpoint is a deadline snapshot. Between deadlines it cannot prove the manager has made no private transfers. V2 never upgrades it to current merely because it is the newest public row. A deadline snapshot may become current only through a scoped, attributable, unexpired immutable attestation that explicitly confirms there are no unrecorded transfers, or through a complete current-state override artifact.

## Exact state fields

`ManagerStateId` is deterministic semantic identity over:

- season and entry ID;
- decision Gameweek;
- active `RuleSetId`;
- currentness scope;
- bank in integer tenths;
- free transfers, including zero;
- exact permanent 15;
- for every owned player: Official FPL ID, club, position, purchase basis, current Official price and realised selling price;
- chips used;
- chronological transfer ledger;
- immutable provenance artifact IDs.

No float-valued money is accepted.

## Selling price

For 2026/27 the RuleSet encodes the verified official mechanic:

- if current price is at or below purchase price, the fall passes through in full;
- if current price has risen, every £0.2 rise realises £0.1 profit.

The core therefore operates in tenths. Examples for a £5.0 purchase basis:

- current £4.9 -> sell £4.9;
- current £5.0 -> sell £5.0;
- current £5.1 -> sell £5.0;
- current £5.2 -> sell £5.1;
- current £5.3 -> sell £5.1;
- current £5.4 -> sell £5.2.

Selling a player and buying him again resets the purchase basis to the rebuy price. Chronological ownership history is therefore decision-critical.

## Transfer ledger

Every permanent transfer event records:

- immutable event ID and sequence;
- Gameweek;
- outgoing/incoming Official IDs;
- outgoing purchase basis and current price;
- recomputed realised sale;
- incoming purchase price;
- bank before/after;
- FT before/after;
- exact hit points;
- normal or Wildcard mode;
- source artifact provenance.

Validation independently recomputes the selling value, bank equation, FT transition and hit. Adjacent events must chain financially and chronologically. Tampering blocks state use.

Normal transfers consume an available FT; once FT is zero each additional transfer carries the RuleSet hit cost. Wildcard transfers are permanent, charge no hit and preserve banked FT. Free Hit is deliberately not represented as a permanent transfer mode because its squad is temporary.

If a caller records normal transfers and later attempts to retroactively reinterpret that window as Wildcard/Free Hit, V2 fails closed and requires the window to be replayed under the correct mode.

## Initial budget versus in-season team value

The £100.0m rule constrains initial squad construction. It is **not** reapplied to an already-owned squad's current market value. A successful team can legitimately exceed £100m after price rises.

For in-season transfers, affordability is instead proven by:

`bank_after = bank_before + realised_sale - incoming_purchase_price`

and `bank_after >= 0`, together with exact position/club/squad rules.

## Price refresh

A current Official-FPL price surface must cover all 15 owned IDs. `reprice_manager_state()` keeps purchase bases fixed, replaces current prices and recomputes every realised selling value. Missing owned IDs or invalid prices block the refresh.

## Chips and FT state

FT may legally be zero during a transfer window. At a normal deadline the RuleSet grant rolls the remaining bank up to the five-transfer maximum. Wildcard and Free Hit preserve banked FT. Chip use is checked for set, Gameweek, one-chip-per-GW and current 2026/27 restrictions.

Wildcard and Free Hit cannot be used to silently erase already-recorded normal permanent-transfer history.

## Full override contract

V1's loose CSV/YAML manual state is not V2 authority.

A V2 override must be one complete JSON artifact that is:

- stored byte-for-byte in `ArtifactStore`;
- attributable to an author;
- justified with a reason;
- timestamped and expiring;
- scoped to a complete season/entry/Gameweek state;
- bound to the active RuleSet;
- complete for all 15 ownership bases/current/selling values, bank and FT;
- complete for chip/transfer ledger fields;
- linked to underlying source artifacts.

Partial patches do not qualify. A wrong selling value, invalid RuleSet, expired override, malformed ledger or incomplete 15 blocks the override.

Overrides describe manager/account facts only. They cannot edit player xP, source reliability, policy thresholds or Official FPL identity.

## V1 migration boundary

`src/apex_fpl/services/team_state.py` remains compatibility code during migration. Its float money, permissive manual files, approximate selling-price fallback and public-snapshot currentness semantics are not V2 authority.

Cutover must route in-season decisions through the V2 `ManagerStateId` contract and its required proof obligation before the V1 state path can be removed.
