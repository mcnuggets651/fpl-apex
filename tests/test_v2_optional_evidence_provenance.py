from __future__ import annotations

from apex.runtime.acquire import (
    _canonical_records_hash,
    _validate_evidence_acquisition,
    _validate_evidence_manifest,
)


def test_optional_missing_evidence_manifest_is_self_consistent(tmp_path):
    records = ()
    manifest = _validate_evidence_acquisition(
        tmp_path / "missing-evidence-manifest.json",
        records,
        required=False,
        official_hash="official-final-hash",
        target_gameweek=4,
    )

    assert manifest["mode"] == "NOT_REQUIRED"
    assert manifest["required"] is False
    assert manifest["completed"] is False
    assert manifest["observed_official_hash"] == "official-final-hash"
    assert manifest["target_gameweek"] == 4
    assert manifest["record_count"] == 0
    assert manifest["records_sha256"] == _canonical_records_hash(records)
    assert manifest["required_source_failures"] == []

    assert _validate_evidence_manifest(
        manifest,
        records,
        required=False,
        official_hash="official-final-hash",
        target_gameweek=4,
    ) == manifest
