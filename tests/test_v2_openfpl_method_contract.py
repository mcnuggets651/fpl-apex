from __future__ import annotations

import copy
import json
from pathlib import Path

import yaml

from apex.forecast.openfpl_governance import validate_method_contract

ROOT = Path(__file__).resolve().parents[1]


def _inputs():
    contract = yaml.safe_load(
        (ROOT / "config/openfpl_method_contract.yaml").read_text(encoding="utf-8")
    )
    policy = yaml.safe_load(
        (ROOT / "config/openfpl_training_policy.yaml").read_text(encoding="utf-8")
    )
    locks = json.loads((ROOT / "upstreams.lock.json").read_text(encoding="utf-8"))
    return contract, policy, locks


def test_governed_method_contract_is_self_consistent():
    contract, policy, locks = _inputs()
    assert validate_method_contract(contract, policy, locks) == ()
    assert contract["position_feature_contract"]["GK"]["current_feature_count"] == 176
    assert contract["position_feature_contract"]["DEF"]["current_feature_count"] == 186
    assert contract["position_feature_contract"]["MID"]["current_feature_count"] == 186
    assert contract["position_feature_contract"]["FWD"]["current_feature_count"] == 186


def test_contract_rejects_score_dependent_feature_reintroduction():
    contract, policy, locks = _inputs()
    mutated = copy.deepcopy(contract)
    mutated["player_families"]["common_current"].append("bps")
    errors = validate_method_contract(mutated, policy, locks)
    assert any("banned scoring-dependent feature remains active: bps" in error for error in errors)


def test_contract_rejects_feature_count_drift():
    contract, policy, locks = _inputs()
    mutated = copy.deepcopy(contract)
    mutated["position_feature_contract"]["GK"]["current_feature_count"] = 177
    errors = validate_method_contract(mutated, policy, locks)
    assert any("GK feature count must be 176" in error for error in errors)


def test_contract_rejects_upstream_pin_drift():
    contract, policy, locks = _inputs()
    mutated = copy.deepcopy(contract)
    mutated["upstream_commit"] = "0" * 40
    errors = validate_method_contract(mutated, policy, locks)
    assert any("commit differs from upstream lock" in error for error in errors)


def test_contract_rejects_claim_of_exact_upstream_training_reproduction():
    contract, policy, locks = _inputs()
    mutated = copy.deepcopy(contract)
    mutated["exact_upstream_training_reproduction_claim"] = True
    errors = validate_method_contract(mutated, policy, locks)
    assert any("cannot claim exact upstream training reproduction" in error for error in errors)


def test_contract_rejects_shortened_history_gate():
    contract, policy, locks = _inputs()
    mutated = copy.deepcopy(contract)
    mutated["build_gates"]["minimum_completed_exact_rule_gameweeks"] = 1
    errors = validate_method_contract(mutated, policy, locks)
    assert any("minimum exact-rule gameweeks differ" in error for error in errors)


def test_contract_rejects_ensemble_drift():
    contract, policy, locks = _inputs()
    mutated = copy.deepcopy(contract)
    mutated["training"]["ensemble"]["aggregation"] = "mean"
    errors = validate_method_contract(mutated, policy, locks)
    assert any("median of 50 models" in error for error in errors)
