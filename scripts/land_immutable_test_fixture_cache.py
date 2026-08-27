from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one target, found {count}: {old[:160]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


cache_path = Path("tests/immutable_fixture_cache.py")
cache_path.write_text(
    '''from __future__ import annotations

import atexit
from pathlib import Path
import shutil
import tempfile
from threading import RLock
from typing import Hashable


_LOCK = RLock()
_CACHE: dict[tuple[str, Hashable], tuple[Path, object]] = {}


def _store_root(store: object) -> Path | None:
    root = getattr(store, "root", None)
    if root is None:
        delegate = getattr(store, "delegate", None)
        root = getattr(delegate, "root", None)
    return None if root is None else Path(root)


def restore_cached_fixture(
    namespace: str,
    key: Hashable,
    *,
    store: object,
) -> object | None:
    """Clone pristine immutable fixture bytes into one isolated filesystem-backed store.

    Only synthetic evidence *generation* is cached. Production/control replay remains live in
    every test and still re-reads, hashes, reconstructs and verifies the cloned artifacts.
    Non-filesystem stores deliberately bypass this optimization.
    """

    root = _store_root(store)
    if root is None:
        return None
    with _LOCK:
        cached = _CACHE.get((namespace, key))
        if cached is None:
            return None
        snapshot_root, value = cached
        source_objects = snapshot_root / "objects"
        if source_objects.exists():
            shutil.copytree(source_objects, root / "objects", dirs_exist_ok=True)
        return value


def retain_cached_fixture(
    namespace: str,
    key: Hashable,
    value: object,
    *,
    store: object,
) -> object:
    """Retain a corruption-isolated pristine copy of deterministic test fixture bytes."""

    root = _store_root(store)
    if root is None:
        return value
    with _LOCK:
        cache_key = (namespace, key)
        if cache_key in _CACHE:
            return value
        snapshot_root = Path(tempfile.mkdtemp(prefix="apex-immutable-fixture-"))
        source_objects = root / "objects"
        if source_objects.exists():
            shutil.copytree(source_objects, snapshot_root / "objects")
        _CACHE[cache_key] = (snapshot_root, value)
    return value


def _cleanup() -> None:
    with _LOCK:
        snapshots = {snapshot for snapshot, _ in _CACHE.values()}
        _CACHE.clear()
    for snapshot in snapshots:
        shutil.rmtree(snapshot, ignore_errors=True)


atexit.register(_cleanup)
''',
    encoding="utf-8",
)

# Cache the deterministic planning fixture once per semantic production-control test world.
path = "tests/production_planning_bundle_helpers.py"
replace_once(
    path,
    "from empirical_qualification_helpers import synthetic_supported_qualification_artifact\n",
    "from empirical_qualification_helpers import synthetic_supported_qualification_artifact\n"
    "from immutable_fixture_cache import restore_cached_fixture, retain_cached_fixture\n",
)
replace_once(
    path,
    '''    Positive chip option values also force a non-zero retained terminal reserve.\n    """\n\n    ruleset = load_ruleset(Path("config/rules/2026-2027.yaml"))\n''',
    '''    Positive chip option values also force a non-zero retained terminal reserve.\n    """\n\n    cache_key = (season, entry, gameweek)\n    cached = restore_cached_fixture(\n        "production-planning-bundle",\n        cache_key,\n        store=store,\n    )\n    if cached is not None:\n        if not isinstance(cached, SyntheticPlanningBundleFixture):\n            raise TypeError("production planning fixture cache type mismatch")\n        return cached\n\n    ruleset = load_ruleset(Path("config/rules/2026-2027.yaml"))\n''',
)
replace_once(
    path,
    '''    return SyntheticPlanningBundleFixture(\n        bundle=bundle,\n        manager_state=manager_state,\n        direct_qualifications=direct,\n    )\n''',
    '''    fixture = SyntheticPlanningBundleFixture(\n        bundle=bundle,\n        manager_state=manager_state,\n        direct_qualifications=direct,\n    )\n    cached_fixture = retain_cached_fixture(\n        "production-planning-bundle",\n        cache_key,\n        fixture,\n        store=store,\n    )\n    if not isinstance(cached_fixture, SyntheticPlanningBundleFixture):\n        raise TypeError("production planning fixture cache type mismatch")\n    return cached_fixture\n''',
)

# Cache synthetic champion-admission/generation construction, never its production verifier.
path = "tests/champion_authority_helpers.py"
replace_once(
    path,
    "from learning_promotion_helpers import synthetic_promoted_model_registry_generation\n",
    "from immutable_fixture_cache import restore_cached_fixture, retain_cached_fixture\n"
    "from learning_promotion_helpers import synthetic_promoted_model_registry_generation\n",
)
replace_once(
    path,
    '''    """Build mechanism-only authority evidence; never real production admission evidence."""\n\n    season = fixture.bundle.season\n''',
    '''    """Build mechanism-only authority evidence; never real production admission evidence."""\n\n    season = fixture.bundle.season\n    cache_key = (\n        season,\n        str(fixture.bundle.bundle_id),\n        reviewed_at,\n        current_generation_artifact_id,\n        expected_parent_generation_id,\n    )\n    cached = restore_cached_fixture(\n        "production-champion-authority",\n        cache_key,\n        store=store,\n    )\n    if cached is not None:\n        if not isinstance(cached, SyntheticChampionAuthorityFixture):\n            raise TypeError("champion authority fixture cache type mismatch")\n        return cached\n''',
)
replace_once(
    path,
    '''    return SyntheticChampionAuthorityFixture(\n        generation=stored_generation,\n        forecast_registry_generation_artifact_id=registry_artifact_id,\n        decision_policy_admission=policy_admission,\n        scenario_generator_admission=generator_admission,\n        scenario_policy_admission=scenario_policy_admission,\n    )\n''',
    '''    authority_fixture = SyntheticChampionAuthorityFixture(\n        generation=stored_generation,\n        forecast_registry_generation_artifact_id=registry_artifact_id,\n        decision_policy_admission=policy_admission,\n        scenario_generator_admission=generator_admission,\n        scenario_policy_admission=scenario_policy_admission,\n    )\n    cached_fixture = retain_cached_fixture(\n        "production-champion-authority",\n        cache_key,\n        authority_fixture,\n        store=store,\n    )\n    if not isinstance(cached_fixture, SyntheticChampionAuthorityFixture):\n        raise TypeError("champion authority fixture cache type mismatch")\n    return cached_fixture\n''',
)

# Cache deterministic reference-solver evidence generation; replay remains uncached at cutover.
path = "tests/reference_solver_planning_helpers.py"
replace_once(
    path,
    "from reference_solver_planning_finance_case import store_finance_qualification_case\n",
    "from immutable_fixture_cache import restore_cached_fixture, retain_cached_fixture\n"
    "from reference_solver_planning_finance_case import store_finance_qualification_case\n",
)
replace_once(
    path,
    '''    synthetic mechanism evidence only and never production qualification evidence.\n    """\n\n    verified = load_production_planning_bundle(fixture.bundle.bundle_id, store=store)\n''',
    '''    synthetic mechanism evidence only and never production qualification evidence.\n    """\n\n    cache_key = str(fixture.bundle.bundle_id)\n    cached = restore_cached_fixture(\n        "planning-reference-solver-material",\n        cache_key,\n        store=store,\n    )\n    if cached is not None:\n        if not isinstance(cached, SyntheticPlanningParityMaterial):\n            raise TypeError("planning parity fixture cache type mismatch")\n        return cached\n\n    verified = load_production_planning_bundle(fixture.bundle.bundle_id, store=store)\n''',
)
replace_once(
    path,
    '''    return SyntheticPlanningParityMaterial(\n        planning_result_id=str(verified.decision.planning_result_id),\n        certificate_artifact_id=stored_certificate.artifact_id,\n        certificate_id=str(certificate.certificate_id),\n        authorization_artifact_id=authorization.artifact_id,\n        authorization_id=authorization.authorization.authorization_id,\n        qualification_artifact_id=qualification_artifact_id,\n        registry_artifact_id=authorization.authorization.registry_artifact_id,\n        corpus_artifact_id=corpus_artifact_id,\n        worker_code_artifact_id=worker_code_artifact_id,\n    )\n''',
    '''    material = SyntheticPlanningParityMaterial(\n        planning_result_id=str(verified.decision.planning_result_id),\n        certificate_artifact_id=stored_certificate.artifact_id,\n        certificate_id=str(certificate.certificate_id),\n        authorization_artifact_id=authorization.artifact_id,\n        authorization_id=authorization.authorization.authorization_id,\n        qualification_artifact_id=qualification_artifact_id,\n        registry_artifact_id=authorization.authorization.registry_artifact_id,\n        corpus_artifact_id=corpus_artifact_id,\n        worker_code_artifact_id=worker_code_artifact_id,\n    )\n    cached_material = retain_cached_fixture(\n        "planning-reference-solver-material",\n        cache_key,\n        material,\n        store=store,\n    )\n    if not isinstance(cached_material, SyntheticPlanningParityMaterial):\n        raise TypeError("planning parity fixture cache type mismatch")\n    return cached_material\n''',
)

# Remove the duplicate planning + champion construction inside _case when _execute already
# has the exact fixture/authority. This changes only test evidence setup, not cutover semantics.
path = "tests/test_v2_production_cutover.py"
replace_once(
    path,
    '''def _case(\n    store,\n    claim_artifact: str,\n    *,\n    missing: str | None = None,\n    inconclusive: str | None = None,\n    scope: str = SCOPE,\n    unrelated_learning_proof: str | None = None,\n) -> AssuranceCase:\n    fixture = _fixture(store)\n    authority = synthetic_production_champion_authority(\n        store=store,\n        fixture=fixture,\n        reviewed_at=CREATED_AT,\n    )\n    verified_bundle = load_production_planning_bundle(fixture.bundle.bundle_id, store=store)\n    verified_generation = verify_bundle_champion_authority(\n        authority.generation.artifact_id,\n        verified_bundle=verified_bundle,\n        as_of=CREATED_AT,\n        store=store,\n    )\n    learning = verify_forecast_registry_champion(\n        verified_generation.generation.forecast_registry_generation_artifact_id,\n        season=SEASON,\n        as_of=verified_generation.generation.authorized_at,\n        store=store,\n    )\n''',
    '''def _case(\n    store,\n    claim_artifact: str,\n    *,\n    missing: str | None = None,\n    inconclusive: str | None = None,\n    scope: str = SCOPE,\n    unrelated_learning_proof: str | None = None,\n    fixture=None,\n    authority=None,\n) -> AssuranceCase:\n    fixture = fixture or _fixture(store)\n    authority = authority or synthetic_production_champion_authority(\n        store=store,\n        fixture=fixture,\n        reviewed_at=CREATED_AT,\n    )\n    learning = verify_forecast_registry_champion(\n        authority.forecast_registry_generation_artifact_id,\n        season=SEASON,\n        as_of=CREATED_AT,\n        store=store,\n    )\n''',
)
replace_once(
    path,
    '''        assurance_case=case or _case(store, claim_artifact),\n''',
    '''        assurance_case=case or _case(\n            store,\n            claim_artifact,\n            fixture=fixture,\n            authority=(\n                None\n                if champion_artifact_id is None\n                else synthetic_production_champion_authority(\n                    store=store,\n                    fixture=fixture,\n                    reviewed_at=CREATED_AT,\n                )\n            ),\n        ),\n''',
)

# Remove imports that became unnecessary after eliminating bundle-authority replay in _case.
replace_once(
    path,
    "from apex_fpl.control.champion_authority import verify_bundle_champion_authority\n",
    "",
)
replace_once(
    path,
    "from apex_fpl.control.production_planning_bundle import load_production_planning_bundle\n",
    "",
)

print("immutable synthetic fixture cache + cutover harness reuse applied")
