from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from apex.runtime.config import ApexConfig


def _payload() -> dict:
    return {
        "schema_version": 1,
        "season": "2026-2027",
        "entry_id": 63984,
        "max_horizon": 8,
        "scoring_rules_version": "fpl-2026-27-v1",
        "snapshot_dir": "data/v2/snapshots",
        "release_prefix": "apex-v2",
        "evidence": {
            "required": True,
            "sources_path": "config/news_sources.yaml",
            "records_path": "acquisition/evidence/hard.json",
            "manifest_path": "acquisition/evidence/acquisition.json",
        },
        "providers": [
            {
                "id": "airsenal",
                "role": "CHAMPION",
                "priority": 0,
                "serve_authorized": True,
                "predictive_status": "INSUFFICIENT_HISTORY",
                "max_age_hours": 18,
                "requested_horizons": [1, 2, 3, 4, 5, 6, 7, 8],
                "path": "acquisition/providers/airsenal.csv",
            },
            {
                "id": "dastan",
                "role": "SHADOW",
                "priority": 10,
                "serve_authorized": False,
                "predictive_status": "INSUFFICIENT_HISTORY",
                "max_age_hours": 18,
                "requested_horizons": [1],
                "path": "acquisition/providers/dastan.csv",
            },
        ],
    }


def _load(tmp_path: Path, payload: dict) -> ApexConfig:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return ApexConfig.load(path)


def test_config_rejects_string_serve_authorized(tmp_path: Path):
    payload = _payload()
    payload["providers"][1]["serve_authorized"] = "false"
    with pytest.raises(ValueError, match="serve_authorized"):
        _load(tmp_path, payload)


def test_config_rejects_string_evidence_required(tmp_path: Path):
    payload = _payload()
    payload["evidence"]["required"] = "false"
    with pytest.raises(ValueError, match="evidence.*required|required.*evidence"):
        _load(tmp_path, payload)


def test_config_rejects_duplicate_provider_ids(tmp_path: Path):
    payload = _payload()
    duplicate = deepcopy(payload["providers"][0])
    duplicate["priority"] = 99
    payload["providers"].append(duplicate)
    with pytest.raises(ValueError, match="duplicate provider"):
        _load(tmp_path, payload)


def test_config_rejects_nonpositive_max_horizon(tmp_path: Path):
    payload = _payload()
    payload["max_horizon"] = 0
    with pytest.raises(ValueError, match="max_horizon"):
        _load(tmp_path, payload)


def test_config_rejects_requested_horizon_outside_max(tmp_path: Path):
    payload = _payload()
    payload["providers"][0]["requested_horizons"] = [1, 9]
    with pytest.raises(ValueError, match="requested_horizons"):
        _load(tmp_path, payload)


def test_config_rejects_nonpositive_provider_max_age(tmp_path: Path):
    payload = _payload()
    payload["providers"][0]["max_age_hours"] = 0
    with pytest.raises(ValueError, match="max_age_hours"):
        _load(tmp_path, payload)
