# Joint-path production promotion

The transfer-aware GW1-GW8 selector is allowed to replace the static exact-horizon starting squad only when all of the following hold on the same sealed decision bundle:

- joint-path solve status is `optimal`;
- the small candidate pool and expanded candidate pool select the same starting 15;
- the joint-path objective improves on the static-path objective by at least 0.25 expected points;
- the existing canonical fallback is already `ready_to_act=true`;
- the post-promotion answer context remains `safe_to_act=true`.

The pathway objective uses exact GW1 mechanics plus the existing legal GW2-GW8 transfer MILP, including rolled free transfers, cash/bank constraints, current selling prices and explicit transfer-hit costs. Future transfers remain contingencies and must be re-solved before every deadline. Current official prices are held fixed across the planning horizon; speculative future price rises are not forecast.

If any promotion condition fails, the existing exact static-horizon canonical selector remains authoritative.
