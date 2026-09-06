# Apex V2 Reproducibility, Provenance and SBOM Contract

## Purpose

Apex V2 must be reproducible from an exact source identity and an exact execution environment. A passing test suite against an unconstrained resolver is insufficient for production promotion because a future dependency release could change solver behaviour, serialization, HTTP semantics or security properties without changing the Apex engine SHA.

## Sealed reference environment

The hardened V2 candidate uses:

- CPython **3.12.14** exactly;
- `pip==26.2.1`;
- `setuptools==80.9.0`;
- `wheel==0.45.1`;
- every runtime and development dependency pinned exactly in `requirements-v2.lock`;
- PEP 517 build isolation disabled after the exact build toolchain is installed, preventing an unrecorded temporary build resolver from selecting different build dependencies.

`pyproject.toml` remains the declaration of supported dependency ranges for package consumers. `requirements-v2.lock` is the production-assurance reference environment used for Apex V2 CI, replay certification and promotion evidence.

## CI invariants

Apex V2 CI must:

1. install the exact Python patch release;
2. install the exact pip/setuptools/wheel toolchain;
3. install Apex plus development dependencies with `--no-build-isolation` and the lock as a constraint;
4. run `pip check`;
5. run `scripts/check_v2_dependency_lock.py`, which rejects missing, mismatched or unlocked installed distributions other than the Apex editable package itself;
6. run the full property/golden/adversarial suite with branch coverage;
7. enforce critical coverage floors;
8. kill the critical semantic mutation sentinels;
9. enforce architecture boundaries and lint;
10. build and retain provenance plus a CycloneDX SBOM.

No dependency range is silently re-resolved during a promotion proof. A dependency upgrade is an explicit source change and therefore receives the same CI, golden replay, mutation and canary treatment as an engine change.

## Provenance artifact

`artifacts/v2/provenance.json` binds the tested candidate to:

- exact engine Git SHA;
- Python implementation and exact version;
- OS release and machine architecture;
- SHA-256 of `pyproject.toml`;
- SHA-256 of `requirements-v2.lock`;
- SHA-256 of the Apex V2 CI workflow;
- SHA-256 of `upstreams.lock.json` when present;
- every exact installed dependency from the lock;
- every immutable 40-hex GitHub Action pin used by the V2 CI workflow.

The artifact deliberately contains no current timestamp. It describes the tested environment and is deterministic for a given source/environment tuple rather than changing simply because CI was rerun later.

## SBOM artifact

`artifacts/v2/sbom.cdx.json` is a CycloneDX 1.6 software bill of materials. It records the Apex V2 application component, the exact engine SHA and one component for every locked Python distribution.

The SBOM is generated only after the installed environment passes lock verification. It therefore cannot attest to one dependency set while tests execute against another.

## Golden replay semantics

Golden replay hashes the same immutable semantic payload used by publication replay verification. Execution-only metadata such as GitHub workflow run ID is not part of the recommendation identity. The test suite separately proves that changing workflow run ID changes the run metadata while leaving the replay-security payload byte-identical.

The following remain inside the semantic replay commitment and must reproduce exactly:

- system decision;
- certification;
- serving-provider policy and qualified horizons;
- contingency state;
- optimiser result and transfer path diagnostics;
- runtime serving health;
- evidence manifest.

## Promotion rule

A successor engine SHA is not eligible for the production pin until:

- the exact locked-environment V2 CI is green;
- static golden semantic digests match;
- mutation sentinels are all killed;
- critical coverage floors pass;
- provenance and SBOM are emitted successfully;
- the main control-plane readiness workflow rehearses that exact SHA in non-serving mode;
- the promotion diff updates only the explicit authority/pin and its governance evidence.

The current production SHA remains the rollback target until the promoted successor passes post-promotion smoke/replay verification.
