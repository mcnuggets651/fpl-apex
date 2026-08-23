# Apex V2 Manager State Authority

## Status

Slice 4 replaces the V1 manager-state authority path with sealed, content-addressed, fail-closed state reconstruction. V1 `src/apex_fpl/services/team_state.py` remains compatibility-only until later legacy removal and cannot establish V2 decision truth.

## Authority chain

A live in-season action may eventually use a `CURRENT_EXACT` `ManagerState` only when its financial facts are proven from immutable inputs.

The normal public reconstruction chain is:

1. **Pre-GW1 GlobalWorld** — Official FPL bootstrap and fixtures are captured and sealed through the V2 acquisition boundary.
2. **GW1 manager-public snapshot** — Official entry summary, history, transfers and GW1 picks are captured byte-for-byte and sealed separately from manager-neutral world data.
3. **InitialManagerBasis** — the original 15 purchase bases are admitted only if the Official bootstrap was captured strictly before the first deadline, every GW1 pick resolves by exact Official FPL ID, squad legality passes the active RuleSet, and calculated bank equals Official GW1 bank.
4. **Current GlobalWorld** — current Official player identity, club, position and price come from a new sealed world.
5. **Current manager-public snapshot** — the target deadline's Official summary/history/transfers/picks are captured and sealed.
6. **HistoricalTransferLedger** — public transfer history is replayed as Official realised sale receipts, purchase prices, bank movements, FT transitions and hit costs. It is persisted as its own immutable artifact.
7. **DEADLINE_SNAPSHOT ManagerState** — current permanent 15, exact purchase bases, exact current Official prices, exact current selling prices, bank, next-window FT state and chip history are reconstructed and validated.
8. **Currentness proof** — a deadline snapshot remains non-actionable until a scoped current-state attestation proves no unrecorded post-deadline changes, or a complete immutable current-state override proves the entire private state.

A missing or contradictory artifact blocks the state instead of creating an approximation.

## Manager-specific acquisition is not GlobalWorld

`GlobalWorld` remains manager-neutral. Entry summary, entry history, transfers and picks are stored in `ManagerPublicSnapshot`, which has a separate semantic `ManagerPublicSnapshotId`.

Retrieval timestamps remain in the raw-capture manifests for freshness and audit, but are excluded from semantic manager snapshot identity. Identical Official response bytes for the same entry/GW therefore produce the same semantic snapshot even if captured at different times.

Replay APIs accept only ArtifactStore references. They expose no network or clock port.

## Historical transfer-price semantics

Official FPL public transfer rows expose:

- `element_in_cost`: the purchase price paid for the incoming player, in integer tenths;
- `element_out_cost`: the realised selling price received for the outgoing player, in integer tenths.

V2 therefore treats `element_out_cost` as an **Official realised sale receipt**. It is not relabelled as the player's historical market price.

This distinction matters because historical public data does not prove the market price that generated a realised sale. Apex does not invent that missing price merely to re-run the half-profit formula.

The two ledgers intentionally have different proof scopes:

- **HistoricalTransferLedger** records Official public realised-sale receipts and reconciles ownership, bank, FT and hit history.
- **ManagerState.transfer_ledger** records live V2 transitions where Apex actually knows the exact current Official market price and can independently prove the RuleSet selling-price formula.

For currently owned players, selling value is always recomputed from exact ownership basis + current Official price + active RuleSet.

## Purchase-basis permanence and rebuys

A player retained from the original squad keeps the pre-GW1 purchase basis. An incoming transfer receives `element_in_cost` as a new basis. If a player is sold and later bought again, the rebuy price becomes the new basis. No earlier ownership basis survives the sale.

Current or predicted prices can never substitute for an unavailable original basis.

## Money and budget semantics

All decision-critical money is integer tenths of £1m. Binary floating point is excluded from the V2 financial truth path.

The £100.0m cap applies to initial squad construction. It is not reapplied to the current market value of an already-owned squad, because legitimate price rises can take an in-season squad above £100.0m. In-season affordability is determined from exact bank + exact realised sale value - exact incoming purchase price.

## Public state versus private current state

Official public picks are deadline snapshots. They do not reveal transfers made after that deadline and before the next one.

Consequently:

- a fully reconciled public reconstruction is `DEADLINE_SNAPSHOT`;
- it cannot silently become `CURRENT_EXACT`;
- currentness requires an attributable, scoped, expiring attestation confirming no unrecorded transfers, or a complete immutable override;
- partial CSV/YAML/manual patches are not V2 authority.

## Full override path

The override adapter stores the complete JSON bytes in ArtifactStore before parsing. It requires author, reason, validity window, full 15-player ownership basis/current/selling values, bank, FT, chip state, complete transfer ledger, underlying source artifacts, explicit current-state confirmation and explicit ledger-completeness confirmation.

Every referenced source artifact must exist and pass hash verification. The resulting state must independently pass the active RuleSet and manager-state invariants.

## Fail-closed conditions

Among other conditions, V2 blocks manager-state authority when:

- pre-GW1 Official prices were not retained before the first deadline;
- the GW1 picks artifact is missing or does not reconcile to the initial bank;
- current Official identity/price coverage is incomplete;
- manager public transfer history is incomplete;
- transfer row counts disagree with Official `event_transfers`;
- reconstructed hits disagree with Official `event_transfers_cost`;
- ownership after replay differs from target published picks;
- reconstructed bank differs from Official published bank;
- transfer chronology is ambiguous in a way that can affect ownership/cash;
- chip history is contradictory or future-dated;
- provenance objects are absent or corrupt;
- the state is only a deadline snapshot when live currentness is required.

## V1 migration boundary

The following V1 behaviors are specifically non-authoritative in V2:

- float-valued bank/prices;
- permissive manual squad/state files;
- treating some selling prices as enough to claim exactness;
- current-price fallback when purchase basis is missing;
- assuming a public deadline snapshot is the manager's current private state;
- using source-controlled/generated files as the live state database;
- using `CachedHttp` or pandas inside the V2 manager-state authority path.

Later cutover slices may remove the V1 implementation only after the V2 decision path, shadow period and release assurance prove it is safe to do so.
