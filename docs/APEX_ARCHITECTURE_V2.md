# Apex V2 Architecture

## Constitutional status

The 23 August 2026 architecture-freeze directive is the governing design contract. V2 is a modular monolith with dependency direction:

`core -> ports <- adapters -> world -> forecast -> decision -> assurance -> control`

Learning is offline and interfaces invoke qualified capabilities. Network access ends at the world seal. Independent/untrusted workers such as AIrsenal and the reference solver execute outside the core runtime dependency graph.

## Change control

A constitutional redesign requires a concrete counterexample, violated invariant, proof that ordinary repair is insufficient, an ADR, a failing reproducer, migration impact and AssuranceCase impact. Otherwise findings are implemented as bugs, experiments, adapters, policies, tests or operations changes.

## Release authority

A release is not authorised by ad-hoc booleans. A machine-readable ProofObligation registry defines mandatory claims. An AssuranceCase links each claim to evidence, tests and artifacts. `ReleaseCertificate` is derived from that case and fails closed on missing, failed or inconclusive mandatory claims.

## Semantic identity

Execution IDs and semantic IDs are separate. Durable semantic content uses the documented restricted canonical JSON profile and SHA-256. Floats cannot silently enter semantic identity; governed numerical values must first pass NumericPolicy quantisation/encoding.
