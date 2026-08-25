"""Canonical Apex V2 production proof contract.

A release caller may supply the proof-obligation snapshot being certified, but it may not
change the constitutional meaning of a mandatory proof ID. Empirical production proofs
also bind to explicit subject kinds so a valid qualification for one object cannot launder
a different composite claim.
"""

from __future__ import annotations

from types import MappingProxyType

from .proofs import ProofClass


_PRODUCTION_PROOF_CLASSES = {
    "PO-RUNTIME-IDENTITY-001": ProofClass.PROVENANCE_ASSERTION,
    "PO-ARTIFACT-INTEGRITY-001": ProofClass.DATA_INTEGRITY_ASSERTION,
    "PO-RELEASE-CAS-001": ProofClass.ALGORITHMIC_CERTIFICATE,
    "PO-GLOBAL-WORLD-SEAL-001": ProofClass.DATA_INTEGRITY_ASSERTION,
    "PO-OFFICIAL-PLAYER-IDENTITY-001": ProofClass.DATA_INTEGRITY_ASSERTION,
    "PO-RULESET-PROVENANCE-001": ProofClass.PROVENANCE_ASSERTION,
    "PO-MANAGER-PUBLIC-SEAL-001": ProofClass.DATA_INTEGRITY_ASSERTION,
    "PO-INITIAL-MANAGER-BASIS-001": ProofClass.DATA_INTEGRITY_ASSERTION,
    "PO-MANAGER-STATE-001": ProofClass.FORMAL_INVARIANT,
    "PO-SOURCE-GOVERNANCE-001": ProofClass.PROVENANCE_ASSERTION,
    "PO-EVIDENCE-LEDGER-001": ProofClass.DATA_INTEGRITY_ASSERTION,
    "PO-FEATURE-TIME-TRAVEL-001": ProofClass.DATA_INTEGRITY_ASSERTION,
    "PO-OUTCOME-TRUTH-001": ProofClass.PROVENANCE_ASSERTION,
    "PO-MINUTES-FEATURE-INPUT-001": ProofClass.DATA_INTEGRITY_ASSERTION,
    "PO-FORECAST-LINEAGE-001": ProofClass.DATA_INTEGRITY_ASSERTION,
    "PO-FORECAST-SCORING-001": ProofClass.ALGORITHMIC_CERTIFICATE,
    "PO-FORECAST-COVERAGE-001": ProofClass.FORMAL_INVARIANT,
    "PO-FORECAST-QUALIFICATION-001": ProofClass.EMPIRICAL_QUALIFICATION,
    "PO-FOOTBALL-UNCERTAINTY-001": ProofClass.IRREDUCIBLY_UNCERTAIN,
    "PO-FPL-LEGALITY-001": ProofClass.FORMAL_INVARIANT,
    "PO-DECISION-MECHANICS-001": ProofClass.ALGORITHMIC_CERTIFICATE,
    "PO-DECISION-SOLVER-EXACTNESS-001": ProofClass.ALGORITHMIC_CERTIFICATE,
    "PO-DECISION-POLICY-QUALIFICATION-001": ProofClass.EMPIRICAL_QUALIFICATION,
    "PO-CANDIDATE-UNIVERSE-001": ProofClass.ALGORITHMIC_CERTIFICATE,
    "PO-DECISION-REPLAY-001": ProofClass.DATA_INTEGRITY_ASSERTION,
    "PO-SCENARIO-CONVERGENCE-001": ProofClass.EMPIRICAL_QUALIFICATION,
    "PO-MECHANICS-RECONCILIATION-001": ProofClass.ALGORITHMIC_CERTIFICATE,
    "PO-REFERENCE-SOLVER-PARITY-001": ProofClass.ALGORITHMIC_CERTIFICATE,
    "PO-LEARNING-NO-HINDSIGHT-001": ProofClass.DATA_INTEGRITY_ASSERTION,
    "PO-MODEL-EVALUATION-001": ProofClass.EMPIRICAL_QUALIFICATION,
    "PO-MODEL-PROMOTION-001": ProofClass.EMPIRICAL_QUALIFICATION,
    "PO-SHADOW-PRODUCTION-001": ProofClass.ALGORITHMIC_CERTIFICATE,
    "PO-PRODUCTION-CUTOVER-001": ProofClass.ALGORITHMIC_CERTIFICATE,
}

PRODUCTION_PROOF_CLASSES = MappingProxyType(_PRODUCTION_PROOF_CLASSES)
EMPIRICAL_PRODUCTION_PROOF_IDS = frozenset(
    proof_id
    for proof_id, proof_class in PRODUCTION_PROOF_CLASSES.items()
    if proof_class is ProofClass.EMPIRICAL_QUALIFICATION
)

_EMPIRICAL_PRODUCTION_SUBJECT_KINDS = {
    "PO-FORECAST-QUALIFICATION-001": frozenset({"apex.forecast-model"}),
    "PO-DECISION-POLICY-QUALIFICATION-001": frozenset({"apex.decision-policy"}),
    "PO-SCENARIO-CONVERGENCE-001": frozenset(
        {
            "apex.scenario-generator",
            "apex.scenario-policy",
            "apex.scenario-convergence",
        }
    ),
    "PO-MODEL-EVALUATION-001": frozenset(
        {
            "apex.learning-policy",
            "apex.model-evaluation",
        }
    ),
    "PO-MODEL-PROMOTION-001": frozenset({"apex.model-promotion"}),
}

PRODUCTION_EMPIRICAL_SUBJECT_KINDS = MappingProxyType(
    _EMPIRICAL_PRODUCTION_SUBJECT_KINDS
)

if set(PRODUCTION_EMPIRICAL_SUBJECT_KINDS) != set(EMPIRICAL_PRODUCTION_PROOF_IDS):
    raise RuntimeError("empirical production subject-kind contract is incomplete")
