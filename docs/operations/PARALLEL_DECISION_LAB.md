# Parallel prospective decision lab

## Purpose

The decision-edge research layer must preserve exact frozen Apex V2 semantics while finishing its predeadline counterfactual commitments reliably. A single controller invocation previously executed several full transfer-horizon MILP optimisations serially. The first live GW3 acceptance run demonstrated that this was operationally unsafe: the workflow reached its 30-minute job ceiling while still inside prospective decision-lab sealing.

The permanent operating contract is therefore **prepare -> parallel immutable task solve -> canonical assemble -> post-outcome score**. This changes wall-clock scheduling only. It does not change the frozen optimiser, provider projections, production recommendation, serving authority or tournament evidence.

Frozen engine SHA:

`99cc7b51b0cff45462b567084cb1844cfe0a456f`

AIrsenal remains the sole serving champion H1-H8. All decision-lab outputs have `production_influence = NONE`, `serving_authorized = false`, `promotion_authority = false` and no automatic serving change authority.

## 1. Prepare

`scripts/apex_v2_decision_lab_parallel.py --mode prepare` discovers immutable tournament-ready candidates that are still before their Official FPL deadline and do not already have a canonical private lab.

For each candidate it reloads the exact immutable public/private source chain, verifies provider artifact hashes, reconstructs the exact private manager context hash, resolves hard exclusions and derives a deterministic experiment plan.

The GitHub Actions matrix is intentionally public-safe. Matrix rows contain only:

- immutable candidate tag;
- deterministic task identifier.

No player IDs, squad IDs, captain, bench, transfer, price or manager-state fields are emitted in the matrix. The workflow explicitly asserts this privacy contract before exposing the matrix as a job output.

The deterministic task plan is provider-neutral. A provider receives only experiments supported by its sealed surface. An H1-only provider therefore receives no fabricated H2+ pure-provider plan. Missing H1 or availability coverage becomes an explicit non-scoreable state rather than an invented forecast.

## 2. Immutable task staging

Each matrix job executes exactly one pre-registered task and writes one immutable private staging release under:

`apex-v2/private-decision-lab-task/<season>/<run-id>/<control-plane-sha-prefix>/<task-id>`

The control-plane SHA is part of both the namespace and task fingerprint. A code revision can never silently reuse a task produced by a different algorithm. A retry on the same code SHA reuses a valid immutable task instead of recomputing it.

Every staging payload binds:

- frozen engine SHA;
- full control-plane SHA;
- candidate tag and candidate readiness hash;
- immutable public attempt/run/snapshot identity;
- Official deadline;
- deterministic plan hash;
- private manager-context hash without publishing manager state;
- hard-exclusion hash;
- exact source projection hashes;
- task kind/provider and any declared overlay fields/horizon;
- sealed decision/result;
- predeadline seal timestamp.

Both the payload seal time and GitHub immutable release publication time must be strictly before the Official deadline. A new task cannot start after the deadline, and a task that finishes after the deadline is refused rather than backdated.

## 3. Wall-clock bound

A staging task may call the full frozen `optimise_transfer_horizon` at most once.

Heavy tasks are:

1. AIrsenal baseline reproduction;
2. challenger H1 + AIrsenal H2+ planning;
3. complete challenger availability fields on unchanged AIrsenal xP;
4. pure-provider contiguous planning when genuine H2+ coverage exists.

H1 mechanics on the already-owned production 15 uses the frozen fixed-squad mechanics path and does not run the transfer-horizon optimiser.

GitHub Actions runs independent staging tasks concurrently with `fail-fast: false` and a bounded matrix. Therefore normal wall-clock cost is approximately the slowest individual task rather than the sum of every provider experiment. A failed task does not invalidate already sealed siblings; rerunning computes only missing tasks on the identical control-plane SHA.

Increasing the old **monolithic** workflow timeout is deliberately not the solution. Parallelisation removes serial accumulation, but each independent exact task must still receive enough time to complete the certified frozen optimiser it invokes.

For the frozen engine the runtime contract is derived from source, not from an observed average:

- `candidate_limit = 8`;
- each SciPy MILP has `time_limit = 120` seconds;
- there is one initial expected-value solve;
- each of up to eight candidate generations can perform two further solves.

Therefore the exact theoretical MILP allowance is:

`(1 + 2 * 8) * 120 = 2040 seconds = 34 minutes`.

That 34 minutes excludes environment setup, controller materialisation, private-store preflight, exact mechanics/rescoring, serialization, immutable release publication and verification, frozen-worktree proof and cleanup. The operations contract therefore requires an additional **15 minutes of orchestration headroom**, giving a minimum compatible matrix-job bound of **49 minutes**. The workflow is configured at **50 minutes**.

`ops_tests/test_apex_v2_decision_lab_runtime_bound.py` reads the exact frozen evaluator materialised by the V2 Ops Contract, statically verifies the audited solve-call shape, derives `candidate_limit` and the per-MILP `time_limit`, and compares the resulting bound plus headroom with the workflow timeout. Optimiser/default drift or a future timeout reduction therefore fails CI and requires an explicit runtime re-audit.

This timeout correction changes only orchestration capacity. It does not reduce candidate depth, shorten the planning horizon, weaken `mip_rel_gap`, skip exact mechanics or alter provider/decision semantics.

## 4. Canonical assembly

The assembler never computes a new counterfactual. It only verifies and packages immutable staging tasks.

For a candidate, assembly requires every task in the deterministic current-control-plane plan. Each staging release must be:

- immutable;
- exact asset set;
- correct private scope;
- exact task fingerprint;
- exact candidate/readiness/plan binding;
- published and payload-sealed before the deadline.

Missing or mismatched required tasks fail closed. No partial canonical lab is published.

The baseline staging task must independently reproduce the immutable production decision signature exactly. If the frozen AIrsenal re-solve disagrees with the production squad, transfers, XI, captain, vice, bench or hit count, canonical assembly is forbidden.

Once every task is valid, the assembler creates the existing canonical lab contract under:

`apex-v2/private-decision-lab/<season>/<run-id>`

Assembly itself may occur after the deadline because it introduces no new forecast or decision: every decision variant it contains was independently committed in an immutable staging release before the deadline. Postdeadline **backfilling of a missing decision task remains forbidden**.

## 5. Realized scoring and sequential learning

After canonical tournament selection and an immutable Official outcome exist, `--mode postoutcome` invokes the existing realized decision-edge scoring and sequential learning contracts.

Realized scoring continues to include legal autosubs, goalkeeper substitution, captain-to-vice fallback, transfer-hit cost, Triple Captain and Bench Boost mechanics. Forecast-accuracy evidence and realized decision-edge evidence remain separate.

One completed canonical H1 is enough for diagnostic learning. Early repeated material edges may enter the owner review queue, but no staging, assembly or learning result can modify serving authority automatically.

## 6. Failure and retry semantics

The pipeline is intentionally resumable:

- **prepare fails:** no task is created;
- **one matrix task fails/times out:** successful sibling task releases remain valid and immutable; canonical assembly does not run;
- **rerun on identical control-plane SHA:** valid existing tasks are verified/reused and only missing tasks execute;
- **rerun after code revision:** new control-plane namespace/fingerprint forces new task evidence;
- **task missing after deadline:** it remains missing forever for that candidate; no hindsight reconstruction;
- **all tasks valid but assembly interrupted:** assembly can safely retry later because it is packaging predeadline immutable decisions only.

There is no partial public manager artifact and no production publisher in this workflow.

## 7. Acceptance contract

A parallel decision-lab change is acceptable only when all of the following are green:

1. full repository pytest and Ruff;
2. upstream and governance consistency checks;
3. Apex V2 Ops Contract against the exact frozen evaluator;
4. operations-only change surface;
5. frozen serving-authority and no-hindsight checks;
6. tests proving provider-neutral H1-only handling;
7. tests proving matrix privacy;
8. tests proving control-plane-bound staging fingerprints;
9. tests proving required-task assembly fails closed;
10. structural test proving the full transfer optimiser has one centralized call site per task;
11. static runtime-bound test proving the per-task timeout covers frozen theoretical MILP allowance plus explicit orchestration headroom;
12. post-merge live workflow completes the GW3 staging matrix and canonical assembly within the operational timeout;
13. immutable canonical GW3 lab is inspected and bound to the expected tournament candidate before the deadline;
14. main and frozen PR #90 identities are reverified afterward.

Only after the live immutable lab exists is the runtime repair considered complete.
