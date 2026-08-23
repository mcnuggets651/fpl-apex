# Apex V2 Proof Obligations

The executable registry is `config/proof_obligations.yaml`.

Each release-critical claim declares its proof class, scope, evidence, executable test route, failure consequence, release applicability and owner. Formal, algorithmic, provenance and integrity claims require `PROVEN`. Empirical qualification and explicitly irreducible uncertainty may be `SUPPORTED` when the registered evidence is sufficient. `FAILED` and `INCONCLUSIVE` never satisfy a mandatory release obligation.

Adding a new mandatory release claim without adding a ProofObligation is a contract violation.
