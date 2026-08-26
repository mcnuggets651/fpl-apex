# Apex V2 Prospective Empirical Operations

This document defines the reviewed operator path between Apex V2's immutable empirical contracts and any future production qualification. It does **not** authorize production by itself.

## Authority boundary

The operator plane is deliberately narrower than the underlying pure replay contracts:

- production storage is PostgreSQL only through `APEX_PRODUCTION_POSTGRES_DSN`;
- there is no filesystem fallback;
- runtime output exposes persisted backend identities, never the DSN or credentials;
- candidate availability/declaration/result times are recorded by the operator process in UTC;
- callers cannot supply `first_available_at`, `declared_at` or `evaluated_at` to backdate evidence;
- known historical outcomes cannot be relabelled as prospective evidence;
- qualification and champion promotion remain separate reviewed operations;
- these commands do not perform production cutover.

The CLI entrypoint is:

```bash
apex-v2 --help
```

## 1. Configure the already-initialised production backend

Runtime credentials must target a PostgreSQL control plane that was administratively initialised and separately qualified. Runtime operations do not create the schema.

```bash
export APEX_PRODUCTION_POSTGRES_DSN='postgresql://...'
export APEX_PRODUCTION_POSTGRES_SCHEMA='apex_v2'   # optional; defaults to apex_v2
apex-v2 backend-identify
```

`backend-identify` must fail closed when the DSN is absent, the control plane is uninitialised or backend identity cannot be replayed. Its output must not contain credentials.

## 2. Seal immutable source evidence

Model parameters, evaluator definitions, experiment policies and outcome evidence must be retained before they are referenced by candidate/experiment records.

```bash
apex-v2 seal-file ./artifact.bin \
  --media-type application/octet-stream \
  --schema-name example-schema \
  --schema-version 1
```

Record the returned `sha256:...` artifact identity. Reusing identical bytes is idempotent.

## 3. Materialize a SHADOW forecast-model candidate

```bash
apex-v2 materialize-model ./forecast-candidate.json
```

The JSON specification supplies model semantics such as model name/version, feature and prediction contracts, retained parameter artifact IDs, valid seasons, training cutoff, qualification season and maximum horizon. The command itself records `first_available_at` and forces `qualification_state=SHADOW` with no qualification artifact.

The result contains:

- immutable candidate artifact ID;
- semantic model ID;
- stable pre-qualification subject ID;
- exact proposed registry row;
- `review_required=true`;
- `champion_changed=false`.

It does not edit `config/forecast_models_v2.yaml` and does not set a champion.

## 4. Materialize a SHADOW receding-horizon DecisionPolicy candidate

```bash
apex-v2 materialize-policy ./decision-policy-candidate.json
```

The command requires replay-valid retained continuation-value, chip-option-value, price-policy and candidate-policy artifacts. Their season/horizon/availability semantics are rechecked. The operator process records candidate availability and forces SHADOW qualification.

It does not edit `config/decision_policies_v2.yaml` and does not set a champion.

## 5. Predeclare the empirical experiment

```bash
apex-v2 experiment-declare \
  sha256:<candidate-artifact> \
  ./experiment-definition.json
```

The definition must identify the exact evaluator artifact, experiment policy artifact, future evaluation window, minimum sample size, metric rules and finite validity horizon. `declared_at` is not accepted from the caller; execution-time UTC is used. Declaration fails if the evaluation window has already started.

The command stores three linked immutable objects:

1. the `ExperimentDefinition`;
2. an `ExperimentRegistry` containing that exact definition;
3. an operator declaration record binding the candidate, definition and registry.

This is the anti-hindsight commitment point. Do not replace it after outcomes are known.

## 6. Record outcomes only after the declared window

```bash
apex-v2 experiment-result \
  sha256:<declaration-artifact> \
  ./experiment-result.json
```

The result specification supplies the sample size, exact metric values and retained source artifact IDs. `evaluated_at` is not accepted from the caller; execution-time UTC is used. The command rejects premature results before the declared evaluation-window end.

Outcome source artifacts must already exist in the same immutable production ArtifactStore.

## 7. Derive and replay empirical qualification

```bash
apex-v2 qualification-derive \
  sha256:<declaration-artifact> \
  sha256:<result-artifact>
```

The certificate is derived from the exact retained candidate, definition, registry and result lineage. Structural mismatch or threshold failure yields `REJECTED`; incomplete sample/metrics yields `INCONCLUSIVE`; only a complete passing experiment yields `SUPPORTED`.

A non-SUPPORTED result exits with status 2. The command never edits a candidate registry or champion.

## 8. Materialize a QUALIFIED candidate proposal

```bash
apex-v2 candidate-qualify \
  sha256:<shadow-candidate-artifact> \
  sha256:<supported-qualification-artifact>
```

The certificate must replay as SUPPORTED for the exact candidate subject, proof ID, season and semantics. The result is a new immutable candidate artifact and exact proposed QUALIFIED registry row.

This operation still returns:

- `review_required=true`;
- `champion_changed=false`.

A reviewed registry-generation/promotion mechanism remains responsible for any champion change. Qualification is evidence; it is not promotion.

## Failure rules

The operator path must fail closed when any of the following occurs:

- production PostgreSQL configuration is absent or invalid;
- referenced source bytes are missing/corrupt;
- a candidate attempts caller-authored availability time;
- an experiment attempts caller-authored declaration time;
- declaration occurs after the window starts;
- a result attempts caller-authored evaluation time;
- a result is recorded before the window ends;
- result/certificate subject, proof, season, evaluator or experiment lineage differs;
- sample size or metrics are incomplete;
- qualification is expired or not yet available at replay time;
- a certificate is not SUPPORTED;
- a DecisionPolicy support artifact is unavailable, wrong-season or wrong-horizon.

## What this slice does not solve

This operator plane removes a software/operations gap. It cannot manufacture the external evidence still required for production:

- a genuinely deployed and operationally qualified shared PostgreSQL control plane;
- future no-hindsight observations covering the declared evaluation windows;
- SUPPORTED empirical qualifications for all mandatory production subjects;
- reviewed champion admissions for forecast model, DecisionPolicy, scenario/dependence and planning reference solver;
- a current replay-valid schema-v2 production planning bundle and complete AssuranceCase;
- an authorized PUBLISHED V2 release.

Until those conditions exist, V2 production cutover remains **WITHHELD**.
