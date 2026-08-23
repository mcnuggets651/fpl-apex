# Apex V2 Assurance Case

An `AssuranceCase` is the machine-readable argument:

`CLAIM -> EVIDENCE -> TEST -> ARTIFACT -> STATUS`

Statuses are `PROVEN`, `SUPPORTED`, `FAILED`, `INCONCLUSIVE` and `NOT_APPLICABLE`.

The case is content identified. A `ReleaseCertificate` is derived by evaluating it against the ProofObligation registry. Missing mandatory proofs fail closed. Formal/software correctness cannot be upgraded from `SUPPORTED` to `PROVEN` merely because a model or workflow looks healthy.
