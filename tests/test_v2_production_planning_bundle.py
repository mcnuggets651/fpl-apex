from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.manager_state_store import store_manager_state
from apex_fpl.control.production_planning_bundle import (
    load_production_planning_bundle,
    store_production_planning_bundle,
)
from apex_fpl.core.canonical import canonical_sha256
from apex_fpl.core.ids import RuleSetId

from production_planning_bundle_helpers import synthetic_production_planning_bundle


def test_schema_v2_planning_bundle_round_trip_replays_exact_lineage(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    fixture = synthetic_production_planning_bundle(store=store)
    verified = load_production_planning_bundle(fixture.bundle.bundle_id, store=store)

    assert str(fixture.bundle.bundle_id) == canonical_sha256(fixture.bundle.semantic_payload())
    assert verified.bundle == fixture.bundle
    assert verified.manager_state.manager_state_id == fixture.bundle.manager_state_id
    assert verified.ruleset.ruleset_id == fixture.bundle.ruleset_id
    assert verified.decision.planning_result_id == fixture.bundle.planning_result_id
    assert verified.decision.selected_action.action_id == verified.robustness_report.ev_anchor_action_id
    assert verified.decision.solver.search_complete is True
    assert verified.decision.solver.gap is not None
    assert verified.decision.solver.gap.numerator == 0


def test_planning_bundle_cannot_swap_current_manager_truth(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    fixture = synthetic_production_planning_bundle(store=store)
    other_source = store.put_bytes(b"other-current-manager-truth").artifact_id
    other_state = replace(
        fixture.manager_state,
        bank_tenths=1,
        provenance_artifact_ids=(other_source,),
    )
    other_id = store_manager_state(other_state, store=store)
    forged = replace(
        fixture.bundle,
        manager_state_id=other_state.manager_state_id,
        manager_state_artifact_id=other_id,
    )
    with pytest.raises(ValueError, match="ManagerState"):
        store_production_planning_bundle(forged, store=store)


def test_planning_bundle_rejects_unretained_ruleset_identity(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    fixture = synthetic_production_planning_bundle(store=store)
    missing_rules = RuleSetId(
        canonical_sha256({"schema_name": "missing-production-ruleset", "version": 1})
    )
    forged = replace(
        fixture.bundle,
        ruleset_id=missing_rules,
        ruleset_artifact_id=str(missing_rules),
    )
    with pytest.raises(ValueError, match="RuleSet artifact failed integrity"):
        store_production_planning_bundle(forged, store=store)


def test_corrupt_retained_ruleset_fails_bundle_replay(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    fixture = synthetic_production_planning_bundle(store=store)
    digest = store._digest_from_id(fixture.bundle.ruleset_artifact_id)
    store._object_path(digest).write_bytes(b"corrupt-rules")
    with pytest.raises(ValueError, match="RuleSet artifact failed integrity"):
        load_production_planning_bundle(fixture.bundle.bundle_id, store=store)
