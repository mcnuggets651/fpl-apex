# Joint GW1-GW8 Initial-Squad Challenger

This diagnostic asks the actual pre-GW1 planning question: which legal GW1 squad
maximises expected points when GW1 is a free initial selection and the transfer
planner is allowed to manage GW2-GW8 with cash, rolled free transfers and explicit
hit costs?

The GW1 squad is no longer sampled from static 1/2/4/8-Gameweek optimisers. It is a
decision variable inside the multi-period path itself. There is no transfer charge
for constructing that initial 15, leftover budget becomes the GW2 bank, and GW2
starts with exactly one free transfer.

The multi-period MILP is a candidate/path generator. Distinct near-optimal GW1
squads are rescored with exact GW1 FPL mechanics and the existing future transfer
planner before comparison with the static production baseline.

Promotion is not automatic. The challenger must solve optimally, beat the current
starting squad on the same pathway objective, and select the same exact-rescored
starting squad under the small candidate-pool sensitivity view and the expanded
candidate pool.

The audit does not forecast future price changes. Stored later transfers are
contingencies only and must be re-solved before every deadline.
