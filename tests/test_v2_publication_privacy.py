from __future__ import annotations

import copy
from pathlib import Path

import pytest

from apex.runtime.acquire import assert_private_manager_credential_opt_in
from apex.runtime.publication import (
    INTENT_FIELDS_V1,
    INTENT_RELEASE_ASSETS_V1,
    PUBLIC_RELEASE_ASSETS_V1,
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
