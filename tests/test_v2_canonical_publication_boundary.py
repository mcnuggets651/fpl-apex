from __future__ import annotations

import json

from apex.runtime.publication import (
    _canonical_forecast_commitment,
    _private_attempt,
    canonical_json_bytes,
    sha256_bytes,
)


def _private_canonical() -> dict:
    return {
        "schema_version": 1,
        "exposure_class": "PRIVATE_MANAGER",
        "season": "2026-2027",
        "target_gameweek": 3,
        "max_contiguous_qualified_horizon": 2,
        "serving_provider_by_horizon": {"1": "airsenal", "2": "airsenal"},
        "provider_versions": {"airsenal": "pinned-sha"},
        "scoring_rules_version": "fpl-2026-27-v1",
        "canonical_projection_sha256": "b" * 64,
        "official": {
            "schema_version": 1,
            "season": "2026-2027",
            "acquired_at": "2026-08-29T12:00:00Z",
            "source_hash": "a" * 64,
            "players": [
                {
                    "element_id": 999,
                    "web_name": "DO_NOT_PUBLISH_PLAYER",
                    "team_id": 1,
                    "position": "MID",
                    "price_tenths": 64,
                    "status": "a",
                    "can_transact": True,
                    "fpl_code": 12345,
                }
            ],
            "fixtures": [
                {
                    "fixture_id": 456,
                    "gameweek": 3,
                    "home_team_id": 1,
                    "away_team_id": 2,
                    "kickoff_time": "2026-09-01T14:00:00Z",
                }
            ],
            "deadlines": {"3": "2026-09-01T12:00:00Z"},
            "teams": [{"id": 1, "name": "Private FC", "short_name": "PVT"}],
        },
        "rows": [
            {
                "element_id": 999,
                "gameweek": 3,
                "horizon": 1,
                "expected_points": 9.99,
                "fixture_ids": [456],
                "n_fixtures": 1,
                "player_status_at_forecast": "a",
                "expected_minutes": 90.0,
                "p_appearance": 1.0,
                "p_start": 1.0,
                "p_60": 1.0,
                "coverage_status": "FORECAST",
                "coverage_reason": None,
                "metadata": {},
                "serving_provider_id": "airsenal",
            }
        ],
    }


def test_public_canonical_asset_is_commitment_only():
    private = _private_canonical()
    public = _canonical_forecast_commitment(private)
    serialized = json.dumps(public, sort_keys=True)

    assert public["schema_version"] == 2
    assert public["content_contract"] == "PROJECTION_COMMITMENT_ONLY_V2"
    assert public["forecast_rows_published"] is False
    assert public["official_catalog_published"] is False
    assert public["projection_row_count"] == 1
    assert public["official_player_count"] == 1
    assert public["official_fixture_count"] == 1
    assert public["private_canonical_forecast_sha256"] == sha256_bytes(
        canonical_json_bytes(private)
    )

    assert "rows" not in public
    assert "official" not in public
    assert "expected_points" not in serialized
    assert "DO_NOT_PUBLISH_PLAYER" not in serialized
    assert "price_tenths" not in serialized
    assert "fixture_id" not in serialized


def test_private_manager_attempt_binds_exact_canonical_surface_hash():
    private = _private_canonical()
    public = _canonical_forecast_commitment(private)
    run = {"season": "2026-2027", "target_gameweek": 3}
    decision = {
        "system_decision": {"decision_mode": "TRANSFER_HORIZON"},
        "provider_diagnostics": {
            "decision_optimisation": {"weeks": []},
        },
    }
    reveal = {
        "schema_version": 1,
        "public_attempt_id": "public-attempt",
        "season": "2026-2027",
        "target_gameweek": 3,
        "decision_mode": "TRANSFER_HORIZON",
    }

    payload = _private_attempt(
        "public-attempt",
        decision,
        {"schema_version": 1, "squad_ids": list(range(1, 16))},
        run,
        bytes(range(32)),
        reveal,
        private,
    )

    assert payload["schema_version"] == 2
    assert payload["canonical_forecast"] == private
    assert payload["canonical_forecast_sha256"] == public[
        "private_canonical_forecast_sha256"
    ]
    assert payload["canonical_forecast_sha256"] == sha256_bytes(
        canonical_json_bytes(payload["canonical_forecast"])
    )
