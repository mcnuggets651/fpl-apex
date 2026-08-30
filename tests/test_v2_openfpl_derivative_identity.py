from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_current_rules_policy_cannot_claim_exact_upstream_training_reproduction():
    policy = yaml.safe_load(
        (ROOT / "config/openfpl_training_policy.yaml").read_text(encoding="utf-8")
    )
    identity = policy["implementation_identity"]

    assert identity["provider_family"] == "openfpl"
    assert identity["upstream_reference_identity"] == "openfpl-reference-inference"
    assert identity["current_rules_identity"] == "apex-openfpl-method-derivative"
    assert identity["exact_upstream_training_reproduction_claim"] is False
    assert identity["source_construction_requires_independent_validation"] is True
    assert "OpenFPL arXiv:2508.09992 methods" in identity["methodology_basis"]
    assert "pinned OpenFPL inference assets and sample schema" in identity["methodology_basis"]
