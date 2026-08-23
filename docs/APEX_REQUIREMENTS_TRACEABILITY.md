# Apex V2 Requirements Traceability

The executable registry is `config/requirements.yaml`.

Every critical requirement must map to architecture invariants, implementation, tests and one or more registered ProofObligations. `RequirementsTraceabilityMatrix.load()` rejects critical orphans and references to unknown proofs.

During incremental migration, future slice implementation markers are explicit rather than pretending incomplete code already exists. Production cutover requires replacing all such markers with concrete implementation paths and leaving zero critical orphans.
