"""Finding 2 regression tests: production_core_sha identity.

These implement the core-promotion and provider-stability regressions from
the FPL Apex red-team review's Finding 2 fix contract. The private query
bridge (a separate repository) selects "latest" by timestamp alone, with no
reference to which production core is CURRENTLY authorized to serve. The
fix on the fpl-apex side is to publish a `production_core_sha` that changes
if and only if governing authority (provider role / serve_authorized /
priority) actually changes -- never on unrelated config edits, and never
merely because the serving provider's name is unchanged while something
else about authority moved.
"""

from __future__ import annotations

from apex.domain.models import ProviderRole, Qualification
from apex.runtime.config import ApexConfig, EvidenceConfig, ProviderConfig, production_core_sha


def _provider(
    provider_id="airsenal",
    role=ProviderRole.CHAMPION,
    priority=0,
    serve_authorized=True,
    path="acquisition/providers/airsenal.csv",
):
    return ProviderConfig(
        provider_id=provider_id,
        role=role,
        priority=priority,
        serve_authorized=serve_authorized,
        max_age_hours=18.0,
        requested_horizons=(1, 2, 3, 4, 5, 6, 7, 8),
        predictive_status=Qualification.INSUFFICIENT_HISTORY,
        path=path,
    )


def _config(providers, scoring_rules_version="fpl-2026-27-v1", **overrides):
    defaults = dict(
        season="2026-2027",
        entry_id=63984,
        max_horizon=8,
        providers=tuple(providers),
        scoring_rules_version=scoring_rules_version,
    )
    defaults.update(overrides)
    return ApexConfig(**defaults)


def test_identical_governance_produces_identical_hash():
    a = _config([_provider()])
    b = _config([_provider()])
    assert production_core_sha(a) == production_core_sha(b)


def test_unrelated_config_fields_do_not_change_the_hash():
    """snapshot_dir, release_prefix and evidence config have no bearing on
    which provider is authorized to serve. Changing them must not move
    production_core_sha -- otherwise every unrelated edit would look like
    an authority change to a consumer comparing hashes."""
    a = _config([_provider()], snapshot_dir="data/v2/snapshots")
    b = _config(
        [_provider()],
        snapshot_dir="data/some/other/path",
        release_prefix="totally-different-prefix",
        evidence=EvidenceConfig(required=True, sources_path="config/other.yaml"),
    )
    assert production_core_sha(a) == production_core_sha(b)


def test_provider_order_in_config_does_not_change_the_hash():
    """The config file may list providers in any order; authority identity
    must not depend on YAML ordering."""
    champion = _provider("airsenal", ProviderRole.CHAMPION, priority=0, serve_authorized=True)
    shadow = _provider("dastan", ProviderRole.SHADOW, priority=10, serve_authorized=False, path="p.csv")
    a = _config([champion, shadow])
    b = _config([shadow, champion])
    assert production_core_sha(a) == production_core_sha(b)


def test_serve_authorized_change_moves_the_hash():
    a = _config([_provider(serve_authorized=True)])
    b = _config([_provider(serve_authorized=False)])
    assert production_core_sha(a) != production_core_sha(b)


def test_role_change_moves_the_hash():
    a = _config([_provider(role=ProviderRole.CHAMPION)])
    b = _config([_provider(role=ProviderRole.SHADOW)])
    assert production_core_sha(a) != production_core_sha(b)


def test_priority_change_moves_the_hash():
    a = _config([_provider(priority=0)])
    b = _config([_provider(priority=1)])
    assert production_core_sha(a) != production_core_sha(b)


def test_scoring_rules_version_change_moves_the_hash():
    a = _config([_provider()], scoring_rules_version="fpl-2026-27-v1")
    b = _config([_provider()], scoring_rules_version="fpl-2027-28-v1")
    assert production_core_sha(a) != production_core_sha(b)


def test_provider_path_does_not_change_the_hash():
    """Where a provider's raw file lives on disk has no bearing on serving
    authority -- only role/serve_authorized/priority/id do."""
    a = _config([_provider(path="acquisition/providers/airsenal.csv")])
    b = _config([_provider(path="some/other/location.csv")])
    assert production_core_sha(a) == production_core_sha(b)


# --- Core-promotion regression (ChatGPT's fixture, Round 8) --------------


def test_core_promotion_regression_provider_stability_cannot_substitute_for_core_identity():
    """The exact scenario the review demanded a regression for: two attempts
    both serve AIrsenal at every horizon (provider identity/serving map is
    IDENTICAL), but authority differs because a different provider's role
    changed underneath the same champion. production_core_sha must still
    detect the difference -- provider-name stability must never be treated
    as proof that authority hasn't moved. This is the exact gap in Claude's
    original (rejected) fix, which suggested serving_provider_by_horizon
    alone was sufficient."""
    core_a = _config(
        [
            _provider("airsenal", ProviderRole.CHAMPION, priority=0, serve_authorized=True),
            _provider("dastan", ProviderRole.SHADOW, priority=10, serve_authorized=False, path="d.csv"),
        ]
    )
    core_b = _config(
        [
            _provider("airsenal", ProviderRole.CHAMPION, priority=0, serve_authorized=True),
            # Same champion (airsenal), same serving map -- but dastan has
            # been promoted to STANDBY. Authority genuinely changed.
            _provider("dastan", ProviderRole.STANDBY, priority=10, serve_authorized=False, path="d.csv"),
        ]
    )
    assert production_core_sha(core_a) != production_core_sha(core_b)


def test_identical_serving_map_and_identical_governance_is_the_same_core():
    """Contrast case: if governance is genuinely unchanged, the hash must be
    stable -- this is what lets a consumer use equality (not just difference)
    as a positive confirmation that authority has not moved."""
    core_a = _config(
        [
            _provider("airsenal", ProviderRole.CHAMPION, priority=0, serve_authorized=True),
            _provider("dastan", ProviderRole.SHADOW, priority=10, serve_authorized=False, path="d.csv"),
        ]
    )
    core_b = _config(
        [
            _provider("airsenal", ProviderRole.CHAMPION, priority=0, serve_authorized=True),
            _provider("dastan", ProviderRole.SHADOW, priority=10, serve_authorized=False, path="d.csv"),
        ]
    )
    assert production_core_sha(core_a) == production_core_sha(core_b)
