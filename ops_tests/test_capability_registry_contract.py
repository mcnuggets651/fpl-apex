from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_capability_registry.py"
SPEC = importlib.util.spec_from_file_location("capability_registry_checker", SCRIPT)
assert SPEC and SPEC.loader
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


class CapabilityRegistryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = checker.load_json_yaml(ROOT / "docs" / "APEX_CAPABILITY_REGISTRY.yaml")
        cls.caps = checker.validate_schema(cls.registry)

    def test_live_registry_has_unique_semantic_capabilities(self) -> None:
        self.assertGreaterEqual(len(self.caps), 40)
        self.assertIn("GOV-003", self.caps)
        self.assertIn("PROD-001", self.caps)
        self.assertIn("PRIV-004", self.caps)
        self.assertIn("INT-001", self.caps)
        self.assertIn("LEG-004", self.caps)

    def test_duplicate_capability_id_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.registry)
        mutated["capabilities"].append(copy.deepcopy(mutated["capabilities"][0]))
        with self.assertRaises(checker.ContractError):
            checker.validate_schema(mutated)

    def test_research_cannot_gain_implicit_serving_influence(self) -> None:
        mutated = copy.deepcopy(self.registry)
        target = next(cap for cap in mutated["capabilities"] if cap["id"] == "RES-001")
        target["production_boundary"]["production_influence"] = "ADVISORY"
        with self.assertRaises(checker.ContractError):
            checker.validate_schema(mutated)

    def test_historical_capability_cannot_be_serving_authorized(self) -> None:
        mutated = copy.deepcopy(self.registry)
        target = next(cap for cap in mutated["capabilities"] if cap["id"] == "LEG-002")
        target["serving_authorized"] = True
        with self.assertRaises(checker.ContractError):
            checker.validate_schema(mutated)

    def test_all_active_workflows_and_apex_v2_scripts_are_registered(self) -> None:
        checker.validate_active_surface(self.caps)

    def test_registry_does_not_copy_authority_shas_or_run_ids(self) -> None:
        checker.validate_no_movable_state(self.registry)

    def test_decision_index_covers_append_only_register(self) -> None:
        checker.validate_decision_index(self.caps)

    def test_constitution_paths_map_to_governance_capability(self) -> None:
        for path in (
            "docs/APEX_CAPABILITY_REGISTRY.yaml",
            "docs/APEX_DECISION_INDEX.yaml",
            "docs/APEX_DECISIONS.md",
            "docs/APEX_ARCHITECTURE.md",
            "scripts/check_capability_registry.py",
            "ops_tests/test_capability_registry_contract.py",
        ):
            self.assertIn("GOV-003", checker.path_capabilities(path, self.caps), path)

    def test_unregistered_path_does_not_get_accidental_capability(self) -> None:
        self.assertEqual(checker.path_capabilities("totally/new/silent_surface.xyz", self.caps), set())

    def test_pr_metadata_parser_is_explicit_not_checkbox_based(self) -> None:
        body = """\
Apex-Capabilities: GOV-003, INT-001
Apex-Authority-Changed: no
Apex-Invariants-Changed: documentation constitution
Apex-Decisions-Reopened: none
"""
        parsed = checker.parse_metadata(body)
        self.assertEqual(parsed["Apex-Capabilities"], "GOV-003, INT-001")
        self.assertEqual(parsed["Apex-Authority-Changed"], "no")

    def test_symbolic_authority_ref_resolves_without_registry_sha_copy(self) -> None:
        authority = json.loads((ROOT / "docs" / "APEX_V2_AUTHORITY.json").read_text(encoding="utf-8"))
        self.assertEqual(
            checker.authority_ref_sha("authority:production_core_sha", authority),
            authority["production_core_sha"],
        )
        self.assertNotIn(authority["production_core_sha"], (ROOT / "docs" / "APEX_CAPABILITY_REGISTRY.yaml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
