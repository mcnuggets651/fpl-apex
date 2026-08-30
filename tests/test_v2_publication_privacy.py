from __future__ import annotations

import copy
import json
import tarfile
from pathlib import Path

import pytest

from apex.runtime.acquire import assert_private_manager_credential_opt_in
from apex.runtime.publication import (
    INTENT_FIELDS_V1,
    INTENT_RELEASE_ASSETS_V1,
    PUBLIC_RELEASE_ASSETS_V1,
    _provider_forecast_archive,
    _governance,
    _manager_actionability,
    _manager_state_mode,
    _required_sha256,
    assert_exact_asset_set,
    make_commitment,
    validate_intent_payload,
)
from apex.runtime.reveal import verify_private_reveal


def test_intent_schema_is_frozen_and_rejects_extra_fields():
    payload = {
        "schema_version": 1,
        "run_id": "r1",
        "season": "2026-2027",
        "gameweek": 3,
        "code_sha": "abc",
        "started_at": "2026-08-29T07:00:00+00:00",
    }
    assert frozenset(payload) == INTENT_FIELDS_V1
    validate_intent_payload(payload)
    with pytest.raises(RuntimeError, match="intent schema field mismatch"):
        validate_intent_payload({**payload, "diagnostic": "must-not-be-added"})


def test_asset_allowlists_are_exact_not_prefix_based(tmp_path: Path):
    intent = tmp_path / "intent.json"
    intent.write_text("{}\n", encoding="utf-8")
    assert_exact_asset_set(
        {"intent.json": intent},
        INTENT_RELEASE_ASSETS_V1,
        "intent",
    )
    extra = tmp_path / "team_state.json"
    extra.write_text("{}\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="asset set mismatch"):
        assert_exact_asset_set(
            {"intent.json": intent, "team_state.json": extra},
            INTENT_RELEASE_ASSETS_V1,
            "intent",
        )


def test_public_release_allowlist_has_exact_six_assets():
    assert PUBLIC_RELEASE_ASSETS_V1 == frozenset(
        {
            "public_attempt.json",
            "canonical_forecast.json",
            "provider_forecasts.tar.gz",
            "governance.json",
            "evidence.json",
            "attestation.json",
        }
    )


def test_pre_gw1_no_public_deadline_is_public_safe_not_private():
    mode, credential_present = _manager_state_mode(
        {
            "mode": "NO_PUBLIC_DEADLINE",
            "credential_present": False,
        }
    )
    assert mode == "NO_PUBLIC_DEADLINE"
    assert credential_present is False


def test_pre_gw1_mode_rejects_any_claimed_owner_credential():
    with pytest.raises(RuntimeError, match="cannot report owner credentials"):
        _manager_state_mode(
            {
                "mode": "NO_PUBLIC_DEADLINE",
                "credential_present": True,
            }
        )


def test_owner_credentials_require_explicit_source_level_opt_in(monkeypatch):
    monkeypatch.setenv("FPL_SESSION_COOKIE", "fake-owner-session")
    monkeypatch.delenv("FPL_X_API_AUTHORIZATION", raising=False)
    monkeypatch.delenv("APEX_ENABLE_PRIVATE_MANAGER_STATE", raising=False)
    with pytest.raises(RuntimeError, match="not explicitly enabled"):
        assert_private_manager_credential_opt_in()

    monkeypatch.setenv("APEX_ENABLE_PRIVATE_MANAGER_STATE", "1")
    assert_private_manager_credential_opt_in()


def test_private_opt_in_without_credentials_fails_closed(monkeypatch):
    monkeypatch.delenv("FPL_SESSION_COOKIE", raising=False)
    monkeypatch.delenv("FPL_X_API_AUTHORIZATION", raising=False)
    monkeypatch.setenv("APEX_ENABLE_PRIVATE_MANAGER_STATE", "1")
    with pytest.raises(RuntimeError, match="no FPL owner credential"):
        assert_private_manager_credential_opt_in()


def test_private_opt_in_rejects_ambiguous_flag(monkeypatch):
    monkeypatch.delenv("FPL_SESSION_COOKIE", raising=False)
    monkeypatch.delenv("FPL_X_API_AUTHORIZATION", raising=False)
    monkeypatch.setenv("APEX_ENABLE_PRIVATE_MANAGER_STATE", "true")
    with pytest.raises(RuntimeError, match="exactly '0' or '1'"):
        assert_private_manager_credential_opt_in()


def test_public_identity_hashes_must_use_real_decision_bundle_digests():
    official_hash = "a" * 64
    canonical_hash = "b" * 64
    decision = {
        "official_snapshot_hash": official_hash,
        "canonical_projection_hash": canonical_hash,
    }
    assert _required_sha256(decision, "official_snapshot_hash") == official_hash
    assert _required_sha256(decision, "canonical_projection_hash") == canonical_hash

    with pytest.raises(RuntimeError, match="not a valid SHA-256"):
        _required_sha256({}, "official_snapshot_hash")
    with pytest.raises(RuntimeError, match="not a valid SHA-256"):
        _required_sha256({"canonical_projection_hash": "not-a-hash"}, "canonical_projection_hash")


def test_public_governance_preserves_degradation_warnings():
    class Snapshot:
        def read_json(self, name):
            assert name == "qualification_matrix.json"
            return []

    acquisition = {
        "mode": "PUBLIC_DEADLINE_FALLBACK",
        "credential_present": False,
        "state_complete_for_transfers": False,
    }
    warning = "serving projection lacks appearance probabilities"
    decision = {
        "certification": {
            "state": "DEGRADED",
            "actionable": True,
            "reasons": [],
            "warnings": [warning],
            "valid_until": "2026-09-04T17:30:00Z",
        },
        "system_decision": {
            "decision_mode": "HOLD_TEAM_STATE_INCOMPLETE"
        },
        "provider_diagnostics": {
            "max_contiguous_horizon": 8,
            "serving_provider_by_horizon": {"1": "airsenal"},
        },
        "evidence_manifest": {},
    }
    governance = _governance(
        Snapshot(),
        decision,
        {"season": "2026-2027", "target_gameweek": 3},
        acquisition,
    )
    assert governance["certification"]["state"] == "DEGRADED"
    assert governance["certification"]["reasons"] == []
    assert governance["certification"]["warnings"] == [warning]


def test_public_deadline_state_is_never_personalized_actionable():
    acquisition = {
        "mode": "PUBLIC_DEADLINE_FALLBACK",
        "credential_present": False,
        "state_complete_for_transfers": False,
    }
    decision = {
        "certification": {"actionable": True},
        "system_decision": {"decision_mode": "HOLD_TEAM_STATE_INCOMPLETE"},
    }
    scoped = _manager_actionability(acquisition, decision)
    assert scoped["engine_actionable"] is True
    assert scoped["manager_state_scope"] == "PUBLIC_LAST_DEADLINE_CONDITIONAL"
    assert scoped["current_editable_team_verified"] is False
    assert scoped["personalized_actionable"] is False
    assert scoped["lineup_actionable"] is False
    assert scoped["transfer_actionable"] is False


def test_authenticated_exact_state_can_be_fully_manager_actionable():
    acquisition = {
        "mode": "AUTHENTICATED_MY_TEAM",
        "credential_present": True,
        "state_complete_for_transfers": True,
    }
    decision = {
        "certification": {"actionable": True},
        "system_decision": {"decision_mode": "TRANSFER_HORIZON"},
    }
    scoped = _manager_actionability(acquisition, decision)
    assert scoped["manager_state_scope"] == "FULL_MANAGER"
    assert scoped["current_editable_team_verified"] is True
    assert scoped["exact_transfer_state_verified"] is True
    assert scoped["personalized_actionable"] is True
    assert scoped["lineup_actionable"] is True
    assert scoped["transfer_actionable"] is True


def test_authenticated_incomplete_transfer_state_scopes_to_current_team_only():
    acquisition = {
        "mode": "AUTHENTICATED_MY_TEAM",
        "credential_present": True,
        "state_complete_for_transfers": False,
    }
    decision = {
        "certification": {"actionable": True},
        "system_decision": {"decision_mode": "HOLD_TEAM_STATE_INCOMPLETE"},
    }
    scoped = _manager_actionability(acquisition, decision)
    assert scoped["manager_state_scope"] == "CURRENT_TEAM_ONLY"
    assert scoped["personalized_actionable"] is True
    assert scoped["lineup_actionable"] is True
    assert scoped["transfer_actionable"] is False



def test_public_provider_archive_contains_provenance_not_forecast_rows(tmp_path: Path):
    from apex.runtime.snapshot import SnapshotBuilder

    builder = SnapshotBuilder()
    builder.add_json(
        "providers/airsenal.json",
        {
            "schema_version": 1,
            "provider_id": "airsenal",
            "provider_version": "upstream-sha",
            "generated_at": "2026-08-29T12:00:00Z",
            "season": "2026-2027",
            "source_snapshot": "official-sha",
            "scoring_rules_version": "fpl-2026-27-v1",
            "supported_horizons": [1, 2],
            "runtime_dependencies": ["python=3.12"],
            "rows": [
                {
                    "element_id": 1,
                    "horizon": 1,
                    "expected_points": 9.9,
                    "metadata": {"must_not_publish": "sentinel"},
                }
            ],
        },
    )
    snapshot = builder.freeze(tmp_path / "snapshots")
    archive_path, entries = _provider_forecast_archive(
        snapshot,
        tmp_path / "provider_forecasts.tar.gz",
    )
    with tarfile.open(archive_path, "r:gz") as archive:
        assert archive.getnames() == ["providers/airsenal.json"]
        member = archive.extractfile("providers/airsenal.json")
        assert member is not None
        published = json.loads(member.read())

    assert published["publication_contract"] == "PROVENANCE_ONLY_V1"
    assert published["forecast_rows_published"] is False
    assert published["provider_id"] == "airsenal"
    assert published["frozen_provider_sha256"] == snapshot.manifest["files"][
        "providers/airsenal.json"
    ]["sha256"]
    assert "rows" not in published
    assert "expected_points" not in published
    assert "sentinel" not in json.dumps(published)
    assert len(entries["providers/airsenal.json"]) == 64

def _commitment_fixture():
    reveal = {
        "schema_version": 1,
        "public_attempt_id": "attempt-123",
        "season": "2026-2027",
        "target_gameweek": 3,
        "decision_mode": "TRANSFER_HORIZON",
        "transfers_in": [44],
        "transfers_out": [12],
        "xi_ids": list(range(1, 12)),
        "captain_id": 1,
        "vice_captain_id": 2,
        "bench_order": [12, 13, 14, 15],
        "objective": 61.2,
        "horizon": 3,
        "transfer_hits": 0,
    }
    key = bytes(range(32))
    commitment, _ = make_commitment(reveal, key=key)
    commitment.update(
        {
            "public_attempt_id": "attempt-123",
            "reveal_not_before": "2026-08-29T10:00:00+00:00",
        }
    )
    public_attempt = {
        "public_attempt_id": "attempt-123",
        "season": "2026-2027",
        "target_gameweek": 3,
        "private_decision_commitment": commitment,
    }
    return reveal, commitment, key, public_attempt


def test_reveal_requires_crypto_identity_and_deadline():
    reveal, commitment, key, public_attempt = _commitment_fixture()

    assert not verify_private_reveal(
        reveal=reveal,
        commitment=commitment,
        key=key,
        public_attempt=public_attempt,
        now="2026-08-29T09:59:59+00:00",
    )
    assert verify_private_reveal(
        reveal=reveal,
        commitment=commitment,
        key=key,
        public_attempt=public_attempt,
        now="2026-08-29T10:00:00+00:00",
    )

    tampered = copy.deepcopy(reveal)
    tampered["captain_id"] = 99
    assert not verify_private_reveal(
        reveal=tampered,
        commitment=commitment,
        key=key,
        public_attempt=public_attempt,
        now="2026-08-29T10:00:00+00:00",
    )

    wrong_identity = {**public_attempt, "public_attempt_id": "other-attempt"}
    assert not verify_private_reveal(
        reveal=reveal,
        commitment=commitment,
        key=key,
        public_attempt=wrong_identity,
        now="2026-08-29T10:00:00+00:00",
    )

    assert not verify_private_reveal(
        reveal=reveal,
        commitment=commitment,
        key=b"x" * 32,
        public_attempt=public_attempt,
        now="2026-08-29T10:00:00+00:00",
    )
