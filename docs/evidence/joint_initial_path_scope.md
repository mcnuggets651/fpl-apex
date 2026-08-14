# Joint GW1-GW8 Initial-Squad Challenger

This diagnostic asks a different question from the current static horizon selector:
which legal GW1 squad maximises total expected points when the existing transfer
MILP is allowed to manage GW2-GW8 with cash, rolled free transfers and explicit
hit costs?

Promotion is not automatic. The challenger must solve optimally, beat the current
starting squad on the same pathway objective, and select the same starting squad
under the small candidate-pool sensitivity view and the full candidate pool.

The audit does not forecast future price changes. Stored later transfers are
contingencies only and must be re-solved before every deadline.
