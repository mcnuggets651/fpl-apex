"""Finding 2: `_public_identity` must surface `production_core_sha` distinct
from `code_sha`/`config_sha`, sourced from `run["production_core_sha"]`
rather than derived, defaulted, or silently omitted.

This is the identity a consumer (the private query bridge, or any future
authority-aware selector) compares against current authority to decide
whether a given public/private attempt pair is still current -- not merely
whether the commit or the whole config file happen to match.
"""

from __future__ import annotations

from apex.runtime.publication import _public_identity


class _Snapshot:
    snapshot_id = "snap-1"
    manifest = {"metadata": {"frozen_at": "2026-08-28T20:19:19+00:00"}}


def _decision():
    return {
        "manifest": {},
        "official_snapshot_hash": "a" * 64,
        "canonical_projection_hash": "b" * 64,
    }


def _run():
    return {
        "season": "2026-2027",
        "target_gameweek": 3,
        "run_id": "run-1",
        "code_sha": "commit-sha-value",
        "config_sha": "raw-config-file-hash",
        "production_core_sha": "governance-only-hash",
    }


def _canonical():
    return {
        "serving_provider_by_horizon": {"1": "airsenal"},
        "max_contiguous_qualified_horizon": 1,
        "scoring_rules_version": "fpl-2026-27-v1",
    }


def test_public_identity_surfaces_production_core_sha_distinctly():
    identity = _public_identity(_Snapshot(), _decision(), _run(), _canonical())
    assert identity["production_core_sha"] == "governance-only-hash"
    # Must be genuinely distinct fields, not aliases of each other.
    assert identity["production_core_sha"] != identity["code_sha"]
    assert identity["production_core_sha"] != identity["config_sha"]


def test_public_identity_fails_loudly_if_run_omits_production_core_sha():
    """If a caller ever forgets to compute production_core_sha into `run`,
    this must fail immediately and loudly (KeyError) rather than silently
    defaulting to None/empty and shipping an unverifiable public attempt."""
    run = _run()
    del run["production_core_sha"]
    try:
        _public_identity(_Snapshot(), _decision(), run, _canonical())
    except KeyError as exc:
        assert "production_core_sha" in str(exc)
    else:
        raise AssertionError("expected KeyError for missing production_core_sha")
