from __future__ import annotations
import argparse
import json
import os
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from apex.domain.models import Position, ProductionProjectionSurface, SystemDecision, dataclass_to_dict
from apex.domain.rules import XI_MAX, XI_MIN, season_rules
from apex.runtime.serde import official_from_dict, projection_from_dict, team_from_dict
from apex_v2_tournament_common import CANDIDATE_PREFIX, SELECTION_PREFIX, TournamentContractError, _find_release, _load_json, _parse_utc, _release_asset_map, _write_json, canonical_sha256, sha256_path
from apex_v2_tournament_ops import _download_candidate, _download_release_files, _load_internal_private_surfaces, _load_private_manager_attempt, _load_private_tournament_surface, _load_selection
FROZEN_APEX_SHA = '99cc7b51b0cff45462b567084cb1844cfe0a456f'
LAB_PREFIX = 'apex-v2/private-decision-lab'
PRIVATE_EDGE_PREFIX = 'apex-v2/private-decision-edge'
LAB_CONTRACT = 'APEX_V2_PRIVATE_DECISION_LAB_V1'
PRIVATE_EDGE_CONTRACT = 'APEX_V2_PRIVATE_DECISION_EDGE_V1'
PRIVATE_EDGE_LEARNING_CONTRACT = 'APEX_V2_PRIVATE_DECISION_EDGE_LEARNING_V1'
LAB_ASSETS = frozenset({'decision_lab.json', 'decision_lab_attestation.json'})
PRIVATE_EDGE_ASSETS = frozenset({'decision_edge.json', 'decision_edge_attestation.json'})
RECENCY_HALF_LIFE_OBSERVATIONS = 4.0
LARGE_EDGE_POINTS = 4.0

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

def _decision_dict(value: SystemDecision | dict[str, Any]) -> dict[str, Any]:
    return dataclass_to_dict(value) if isinstance(value, SystemDecision) else dict(value)

def _surface_hash(surface: dict[str, Any]) -> str:
    return canonical_sha256(surface)

def _production_surface(raw: dict[str, Any]) -> ProductionProjectionSurface:
    parsed = projection_from_dict(raw)
    return ProductionProjectionSurface(parsed.schema_version, parsed.provider_id, parsed.provider_version, parsed.generated_at, parsed.season, parsed.source_snapshot, parsed.scoring_rules_version, parsed.supported_horizons, parsed.rows)

def _row_map(surface: dict[str, Any], *, horizon: int) -> dict[int, dict[str, Any]]:
    output: dict[int, dict[str, Any]] = {}
    for row in surface.get('rows') or []:
        try:
            if int(row.get('horizon', -1)) != int(horizon):
                continue
            if str(row.get('coverage_status') or 'FORECAST').upper() != 'FORECAST':
                continue
            output[int(row['element_id'])] = row
        except (KeyError, TypeError, ValueError):
            continue
    return output

def _complete_expected_points(surface: dict[str, Any], *, horizon: int, required_ids: frozenset[int]) -> bool:
    rows = _row_map(surface, horizon=horizon)
    return all((player_id in rows and rows[player_id].get('expected_points') is not None for player_id in required_ids))

def _contiguous_horizon(surface: dict[str, Any], *, required_ids: frozenset[int], maximum: int) -> int:
    qualified = 0
    for horizon in range(1, int(maximum) + 1):
        if not _complete_expected_points(surface, horizon=horizon, required_ids=required_ids):
            break
        qualified = horizon
    return qualified

def _hybrid_h1_then_airsenal(*, provider_id: str, challenger: dict[str, Any], airsenal: dict[str, Any], max_horizon: int) -> dict[str, Any]:
    rows = [deepcopy(row) for row in challenger.get('rows') or [] if int(row.get('horizon', -1)) == 1]
    rows.extend((deepcopy(row) for row in airsenal.get('rows') or [] if 2 <= int(row.get('horizon', -1)) <= int(max_horizon)))
    return {'schema_version': 1, 'provider_id': f'shadow_h1_{provider_id}_airsenal_future', 'provider_version': f"h1={challenger.get('provider_version')}|future={airsenal.get('provider_version')}", 'generated_at': max(str(challenger.get('generated_at') or ''), str(airsenal.get('generated_at') or '')), 'season': airsenal['season'], 'source_snapshot': airsenal['source_snapshot'], 'scoring_rules_version': airsenal['scoring_rules_version'], 'supported_horizons': list(range(1, int(max_horizon) + 1)), 'runtime_dependencies': ['SHADOW_COUNTERFACTUAL_ONLY', f'H1:{provider_id}', 'H2_PLUS:airsenal'], 'rows': rows}

def _availability_overlay(*, provider_id: str, challenger: dict[str, Any], airsenal: dict[str, Any], required_ids: frozenset[int], max_horizon: int) -> tuple[dict[str, Any], list[str]]:
    challenger_h1 = _row_map(challenger, horizon=1)
    fields = ('expected_minutes', 'p_appearance', 'p_start', 'p_60')
    overlay_fields = [field for field in fields if all((player_id in challenger_h1 and challenger_h1[player_id].get(field) is not None for player_id in required_ids))]
    if not overlay_fields:
        raise TournamentContractError(f'{provider_id} has no complete H1 availability field on the decision universe')
    output = deepcopy(airsenal)
    output['provider_id'] = f'shadow_availability_{provider_id}_on_airsenal'
    output['provider_version'] = f"base={airsenal.get('provider_version')}|availability={challenger.get('provider_version')}"
    output['runtime_dependencies'] = ['SHADOW_COUNTERFACTUAL_ONLY', 'XP:airsenal', f'AVAILABILITY:{provider_id}']
    output['supported_horizons'] = list(range(1, int(max_horizon) + 1))
    for row in output.get('rows') or []:
        if int(row.get('horizon', -1)) != 1:
            continue
        player_id = int(row['element_id'])
        challenger_row = challenger_h1.get(player_id)
        if challenger_row is None:
            continue
        for field in overlay_fields:
            row[field] = challenger_row[field]
        metadata = dict(row.get('metadata') or {})
        metadata['shadow_availability_source'] = provider_id
        metadata['shadow_availability_fields'] = list(overlay_fields)
        row['metadata'] = metadata
    return (output, overlay_fields)

def _hard_exclusions_from_public_evidence(public_files: dict[str, Path], *, gameweek: int) -> frozenset[int]:
    evidence_path = public_files.get('evidence.json')
    if evidence_path is None:
        return frozenset()
    payload = _load_json(evidence_path)
    rows = payload if isinstance(payload, list) else payload.get('rows') or payload.get('records') or payload.get('evidence') or []
    output: set[int] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            if str(row.get('effect') or '') == 'HARD_EXCLUDE' and int(row.get('gameweek') or -1) == int(gameweek):
                output.add(int(row['element_id']))
        except (KeyError, TypeError, ValueError):
            continue
    return frozenset(output)

def _decision_signature(decision: dict[str, Any]) -> dict[str, Any]:
    return {'squad_ids': sorted((int(value) for value in decision.get('squad_ids') or [])), 'xi_ids': sorted((int(value) for value in decision.get('xi_ids') or [])), 'captain_id': int(decision['captain_id']), 'vice_captain_id': int(decision['vice_captain_id']), 'bench_order': [int(value) for value in decision.get('bench_order') or []], 'transfers_in': sorted((int(value) for value in decision.get('transfers_in') or [])), 'transfers_out': sorted((int(value) for value in decision.get('transfers_out') or [])), 'transfer_hits': int(decision.get('transfer_hits') or 0)}

def _variant(*, variant_id: str, kind: str, provider_id: str, decision: SystemDecision | dict[str, Any], source_surface_hashes: dict[str, str], overlay_fields: Iterable[str]=(), note: str='') -> dict[str, Any]:
    payload = _decision_dict(decision)
    return {'variant_id': variant_id, 'variant_kind': kind, 'provider_id': provider_id, 'status': 'SEALED_PREDEADLINE', 'production_influence': 'NONE', 'serving_authorized': False, 'source_surface_hashes': dict(sorted(source_surface_hashes.items())), 'overlay_fields': list(overlay_fields), 'decision': payload, 'decision_signature_sha256': canonical_sha256(_decision_signature(payload)), 'projected_objective': payload.get('objective'), 'note': note}

def build_decision_lab(*, readiness: dict[str, Any], private_attempt: dict[str, Any], surfaces: dict[str, dict[str, Any]], surface_hashes: dict[str, str], public_files: dict[str, Path], control_plane_sha: str) -> dict[str, Any]:
    from apex.decision.mechanics import decision_from_fixed_squad
    from apex.decision.transfers import optimise_transfer_horizon
    if readiness.get('tournament_ready') is not True:
        raise TournamentContractError('decision lab requires a tournament-ready candidate')
    if readiness.get('production_influence') != 'NONE':
        raise TournamentContractError('candidate crossed production boundary')
    seal = readiness.get('common_seal') or {}
    if seal.get('eligible_common_predeadline_candidate') is not True:
        raise TournamentContractError('decision lab requires eligible common predeadline seal')
    deadline = _parse_utc(str(seal['deadline']))
    if _utc_now() >= deadline:
        raise TournamentContractError('postdeadline decision-lab sealing is forbidden')
    target_gameweek = int(readiness['target_gameweek'])
    canonical = private_attempt.get('canonical_forecast') or {}
    official = official_from_dict(canonical.get('official') or {})
    team_raw = private_attempt.get('team_state')
    if not isinstance(team_raw, dict):
        raise TournamentContractError('decision lab requires exact authenticated team state')
    team = team_from_dict(team_raw)
    baseline_raw = private_attempt.get('system_decision')
    if not isinstance(baseline_raw, dict):
        raise TournamentContractError('decision lab requires sealed production decision')
    baseline_signature = _decision_signature(baseline_raw)
    airsenal = surfaces.get('airsenal')
    if airsenal is None:
        raise TournamentContractError('decision lab requires sealed AIrsenal surface')
    if str((readiness.get('production') or {}).get('serving_provider_by_horizon', {}).get('1')) != 'airsenal':
        raise TournamentContractError('decision lab serving baseline is not AIrsenal')
    entrants = [str(value) for value in (readiness.get('universal_h1_league') or {}).get('entrants') or []]
    if 'airsenal' not in entrants:
        raise TournamentContractError('universal H1 field does not contain serving champion')
    missing = [provider_id for provider_id in entrants if provider_id not in surfaces]
    if missing:
        raise TournamentContractError('sealed H1 entrant missing private surface: ' + ', '.join(missing))
    provider_meta = readiness.get('providers') or {}
    for provider_id in entrants:
        expected_hash = str((provider_meta.get(provider_id) or {}).get('artifact_sha256') or '')
        observed_hash = str(surface_hashes.get(provider_id) or '')
        if expected_hash and expected_hash != observed_hash:
            raise TournamentContractError(f'decision-lab provider artifact hash mismatch: {provider_id}')
    decision_universe = official.decision_universe(set(team.squad_ids))
    available_airsenal_horizon = _contiguous_horizon(airsenal, required_ids=decision_universe, maximum=max((int(value) for value in airsenal.get('supported_horizons') or [1])))
    transfer_plan = private_attempt.get('transfer_plan') or []
    if str(baseline_raw.get('decision_mode') or '') == 'TRANSFER_HORIZON':
        if not isinstance(transfer_plan, list) or not transfer_plan:
            raise TournamentContractError('decision lab cannot recover immutable production planning horizon')
        max_horizon = len(transfer_plan)
    else:
        max_horizon = available_airsenal_horizon
    if max_horizon < 2 or max_horizon > available_airsenal_horizon:
        raise TournamentContractError('decision lab production planning horizon is incompatible with sealed AIrsenal coverage')
    excluded_h1 = _hard_exclusions_from_public_evidence(public_files, gameweek=target_gameweek)
    variants: dict[str, dict[str, Any]] = {}
    experiment_matrix: dict[str, dict[str, Any]] = {}
    baseline = _variant(variant_id='production_baseline', kind='PRODUCTION_BASELINE', provider_id='airsenal', decision=baseline_raw, source_surface_hashes={'airsenal': surface_hashes['airsenal']}, note='Exact immutable production decision; comparison anchor only.')
    variants[baseline['variant_id']] = baseline
    airsenal_surface = _production_surface(airsenal)
    recomputed = optimise_transfer_horizon(official, airsenal_surface, team, max_horizon=max_horizon, excluded_h1=excluded_h1)
    if recomputed.decision is None:
        raise TournamentContractError('decision lab could not recompute AIrsenal production decision')
    recomputed_signature = _decision_signature(_decision_dict(recomputed.decision))
    if recomputed_signature != baseline_signature:
        raise TournamentContractError('decision lab AIrsenal recomputation does not match immutable production decision')
    baseline_squad = tuple((int(value) for value in baseline_raw.get('squad_ids') or []))
    if len(baseline_squad) != 15:
        raise TournamentContractError('production baseline does not contain exact final 15')
    for provider_id in entrants:
        if provider_id == 'airsenal':
            continue
        experiment_matrix[provider_id] = {'h1_mechanics': 'PENDING', 'h1_plus_airsenal_future': 'PENDING', 'availability_on_airsenal': 'PENDING', 'pure_provider_plan': 'PENDING'}
        challenger = surfaces[provider_id]
        if not _complete_expected_points(challenger, horizon=1, required_ids=decision_universe):
            experiment_matrix[provider_id]['h1_mechanics'] = 'NOT_SCOREABLE_INCOMPLETE_H1_XP'
            experiment_matrix[provider_id]['h1_plus_airsenal_future'] = 'NOT_SCOREABLE_INCOMPLETE_H1_XP'
            experiment_matrix[provider_id]['availability_on_airsenal'] = 'NOT_SCOREABLE_INCOMPLETE_H1_XP'
            experiment_matrix[provider_id]['pure_provider_plan'] = 'NOT_SCOREABLE_INCOMPLETE_H1_XP'
            continue
        challenger_surface = _production_surface(challenger)
        mechanics_decision = decision_from_fixed_squad(official, challenger_surface, baseline_squad, horizon=1, transfers_in=tuple((int(value) for value in baseline_raw.get('transfers_in') or [])), transfers_out=tuple((int(value) for value in baseline_raw.get('transfers_out') or [])), transfer_hits=int(baseline_raw.get('transfer_hits') or 0), decision_mode=f'SHADOW_H1_MECHANICS_ON_PRODUCTION_SQUAD::{provider_id}', xi_excluded=excluded_h1)
        variants[f'h1_mechanics::{provider_id}'] = _variant(variant_id=f'h1_mechanics::{provider_id}', kind='H1_MECHANICS_ON_PRODUCTION_SQUAD', provider_id=provider_id, decision=mechanics_decision, source_surface_hashes={provider_id: surface_hashes[provider_id], 'airsenal': surface_hashes['airsenal']}, note='Same production transfers/final 15; challenger H1 chooses XI, captain, vice and bench.')
        experiment_matrix[provider_id]['h1_mechanics'] = 'SEALED_PREDEADLINE'
        h1_future = _hybrid_h1_then_airsenal(provider_id=provider_id, challenger=challenger, airsenal=airsenal, max_horizon=max_horizon)
        hybrid_result = optimise_transfer_horizon(official, _production_surface(h1_future), team, max_horizon=max_horizon, excluded_h1=excluded_h1)
        if hybrid_result.decision is not None:
            variants[f'h1_plus_airsenal_future::{provider_id}'] = _variant(variant_id=f'h1_plus_airsenal_future::{provider_id}', kind='CHALLENGER_H1_AIRSENAL_H2_PLUS', provider_id=provider_id, decision=hybrid_result.decision, source_surface_hashes={provider_id: surface_hashes[provider_id], 'airsenal': surface_hashes['airsenal']}, note='Challenger supplies all H1 forecast fields; AIrsenal supplies H2+ planning horizons.')
            experiment_matrix[provider_id]['h1_plus_airsenal_future'] = 'SEALED_PREDEADLINE'
        else:
            experiment_matrix[provider_id]['h1_plus_airsenal_future'] = 'OPTIMISER_NO_DECISION'
        try:
            overlay, overlay_fields = _availability_overlay(provider_id=provider_id, challenger=challenger, airsenal=airsenal, required_ids=decision_universe, max_horizon=max_horizon)
        except TournamentContractError:
            overlay = None
            overlay_fields = []
            experiment_matrix[provider_id]['availability_on_airsenal'] = 'NOT_SCOREABLE_NO_COMPLETE_AVAILABILITY_FIELD'
        if overlay is not None:
            overlay_result = optimise_transfer_horizon(official, _production_surface(overlay), team, max_horizon=max_horizon, excluded_h1=excluded_h1)
            if overlay_result.decision is not None:
                variants[f'availability_on_airsenal::{provider_id}'] = _variant(variant_id=f'availability_on_airsenal::{provider_id}', kind='CHALLENGER_AVAILABILITY_ON_AIRSENAL_XP', provider_id=provider_id, decision=overlay_result.decision, source_surface_hashes={provider_id: surface_hashes[provider_id], 'airsenal': surface_hashes['airsenal']}, overlay_fields=overlay_fields, note='AIrsenal xP is unchanged; only challenger availability fields with 100% decision-universe coverage are substituted.')
                experiment_matrix[provider_id]['availability_on_airsenal'] = 'SEALED_PREDEADLINE'
            else:
                experiment_matrix[provider_id]['availability_on_airsenal'] = 'OPTIMISER_NO_DECISION'
        provider_horizon = _contiguous_horizon(challenger, required_ids=decision_universe, maximum=max_horizon)
        if provider_horizon >= 2:
            pure_result = optimise_transfer_horizon(official, challenger_surface, team, max_horizon=provider_horizon, excluded_h1=excluded_h1)
            if pure_result.decision is not None:
                variants[f'pure_provider_plan::{provider_id}'] = _variant(variant_id=f'pure_provider_plan::{provider_id}', kind='PURE_PROVIDER_CONTIGUOUS_PLAN', provider_id=provider_id, decision=pure_result.decision, source_surface_hashes={provider_id: surface_hashes[provider_id]}, note=f'Provider-only shadow transfer plan over its H1-H{provider_horizon} contiguous qualified surface.')
                experiment_matrix[provider_id]['pure_provider_plan'] = 'SEALED_PREDEADLINE'
            else:
                experiment_matrix[provider_id]['pure_provider_plan'] = 'OPTIMISER_NO_DECISION'
        else:
            experiment_matrix[provider_id]['pure_provider_plan'] = 'NOT_SUPPORTED_H1_ONLY_OR_INCOMPLETE_H2'
    if len(variants) <= 1:
        raise TournamentContractError('decision lab produced no challenger counterfactual')
    return {'schema_version': 1, 'contract': LAB_CONTRACT, 'exposure_class': 'PRIVATE_MANAGER', 'production_influence': 'NONE', 'serving_authorized': False, 'promotion_authority': False, 'automatic_serving_change': False, 'sealed_before_outcomes': True, 'postdeadline_backfill_forbidden': True, 'frozen_engine_sha': FROZEN_APEX_SHA, 'control_plane_sha': control_plane_sha, 'source': {'season': readiness['season'], 'target_gameweek': target_gameweek, 'run_id': seal['run_id'], 'public_attempt_id': seal['public_attempt_id'], 'candidate_release_tag': seal['candidate_release_tag'], 'candidate_readiness_sha256': readiness['readiness_sha256'], 'snapshot_id': seal['snapshot_id'], 'official_snapshot_sha256': seal['official_snapshot_sha256'], 'deadline': seal['deadline']}, 'policy': {'provider_neutral_variants': True, 'dastan_prior_advantage': False, 'h1_mechanics_isolates_lineup_captain_bench': True, 'h1_plus_future_tests_transfer_and_mechanics_impact': True, 'availability_overlay_requires_complete_preoutcome_field': True, 'expected_points_never_rescaled_from_expected_minutes': True, 'no_hindsight_imputation': True}, 'decision_universe_player_count': len(decision_universe), 'decision_universe_player_ids_published': False, 'private_position_map': {str(player.element_id): player.position.value for player in official.players}, 'hard_exclusion_count': len(excluded_h1), 'max_airsenal_planning_horizon': max_horizon, 'team_context': {'active_chip': team.active_chip, 'free_transfers': team.free_transfers, 'bank_tenths': team.bank_tenths}, 'baseline_variant_id': 'production_baseline', 'experiment_matrix': experiment_matrix, 'variants': variants}

def _write_private_release(*, private_store: Any, tag: str, payload: dict[str, Any], payload_name: str, attestation_name: str, scope: str, workdir: Path, title: str) -> str:
    payload_path = _write_json(workdir / payload_name, payload)
    attestation_path = _write_json(workdir / attestation_name, {'schema_version': 1, 'scope': scope, 'payload_sha256': sha256_path(payload_path), 'production_influence': 'NONE', 'serving_authorized': False, 'promotion_authority': False})
    private_store.create_once(tag, {payload_name: payload_path, attestation_name: attestation_path}, target_commitish=None, name=title, body='Immutable private prospective decision research; never a serving authority.')
    return tag

def _load_private_payload(*, store: Any, release: dict[str, Any], payload_name: str, attestation_name: str, expected_assets: frozenset[str], scope: str, workdir: Path) -> dict[str, Any]:
    if release.get('immutable') is not True:
        raise TournamentContractError('private decision research release is mutable')
    if frozenset(_release_asset_map(release)) != expected_assets:
        raise TournamentContractError('private decision research asset set mismatch')
    files = _download_release_files(store, release, expected_assets, workdir)
    attestation = _load_json(files[attestation_name])
    if attestation.get('scope') != scope:
        raise TournamentContractError('private decision research attestation scope mismatch')
    if str(attestation.get('payload_sha256') or '') != sha256_path(files[payload_name]):
        raise TournamentContractError('private decision research digest mismatch')
    payload = _load_json(files[payload_name])
    if payload.get('production_influence') != 'NONE' or payload.get('serving_authorized') is not False:
        raise TournamentContractError('private decision research crossed serving boundary')
    return payload

def _load_candidate_context(*, public_store: Any, private_store: Any, public_releases: list[dict[str, Any]], private_releases: list[dict[str, Any]], candidate_release: dict[str, Any], readiness: dict[str, Any], root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, str], dict[str, Path]]:
    seal = readiness.get('common_seal') or {}
    run_id = str(seal.get('run_id') or '')
    public_attempt_id = str(seal.get('public_attempt_id') or '')
    source_tag = str(seal.get('source_release_tag') or '')
    private_base_tag = str(seal.get('private_base_release_tag') or '')
    if not all((run_id, public_attempt_id, source_tag, private_base_tag)):
        raise TournamentContractError('decision-lab candidate lacks immutable source identities')
    source_release = _find_release(public_releases, source_tag)
    private_base_release = _find_release(private_releases, private_base_tag)
    manager_release = _find_release(private_releases, f"apex-v2/private/{readiness['season']}/{run_id}")
    if source_release is None or private_base_release is None or manager_release is None:
        raise TournamentContractError('decision-lab candidate source/public/private release linkage is incomplete')
    internal, internal_hashes, public_files, public_attempt = _load_internal_private_surfaces(public_store=public_store, private_store=private_store, public_release=source_release, private_release=private_base_release, workdir=root / 'provider-base')
    if str(public_attempt.get('public_attempt_id') or '') != public_attempt_id:
        raise TournamentContractError('decision-lab source public identity mismatch')
    if str(public_attempt.get('run_id') or '') != run_id:
        raise TournamentContractError('decision-lab source run identity mismatch')
    surfaces = dict(internal)
    hashes = dict(internal_hashes)
    supplemental_tag = str(seal.get('private_tournament_release_tag') or '')
    if supplemental_tag:
        supplemental_release = _find_release(private_releases, supplemental_tag)
        if supplemental_release is None:
            raise TournamentContractError('decision-lab private tournament supplement release is missing')
        supplemental, _ = _load_private_tournament_surface(private_store=private_store, release=supplemental_release, public_attempt_id=public_attempt_id, expected_run_id=run_id, workdir=root / 'provider-supplement')
        for provider_id, surface in supplemental.items():
            if provider_id in surfaces:
                raise TournamentContractError(f'decision-lab duplicate supplemental provider: {provider_id}')
            surfaces[provider_id] = surface
            hashes[provider_id] = _surface_hash(surface)
    manager_attempt = _load_private_manager_attempt(private_store=private_store, release=manager_release, public_attempt_id=public_attempt_id, workdir=root / 'manager')
    return (manager_attempt, surfaces, hashes, public_files)

def seal_pending_labs(*, public_store: Any, private_store: Any, season: str, control_plane_sha: str, now: datetime | None=None) -> dict[str, Any]:
    now = (now or _utc_now()).astimezone(timezone.utc)
    public_releases = public_store.list_releases()
    private_releases = private_store.list_releases()
    private_by_tag = {str(row.get('tag_name') or ''): row for row in private_releases if not row.get('draft')}
    sealed: list[str] = []
    existing: list[str] = []
    skipped_postdeadline: list[str] = []
    skipped_not_ready: list[str] = []
    with tempfile.TemporaryDirectory(prefix='apex-decision-lab-') as tmp:
        root = Path(tmp)
        candidates = [release for release in public_releases if str(release.get('tag_name') or '').startswith(f'{CANDIDATE_PREFIX}/{season}/') and (not release.get('draft')) and (release.get('immutable') is True)]
        for release in sorted(candidates, key=lambda row: str(row.get('published_at') or '')):
            readiness = _download_candidate(public_store, release, root / f"candidate-{release['id']}")
            if readiness.get('tournament_ready') is not True:
                skipped_not_ready.append(str(release.get('tag_name') or ''))
                continue
            seal = readiness.get('common_seal') or {}
            run_id = str(seal.get('run_id') or '')
            if not run_id:
                raise TournamentContractError('decision-lab candidate lacks run id')
            tag = f'{LAB_PREFIX}/{season}/{run_id}'
            prior = private_by_tag.get(tag)
            if prior is not None:
                lab = _load_private_payload(store=private_store, release=prior, payload_name='decision_lab.json', attestation_name='decision_lab_attestation.json', expected_assets=LAB_ASSETS, scope='PRIVATE_PROSPECTIVE_DECISION_LAB', workdir=root / f'existing-lab-{run_id}')
                if str((lab.get('source') or {}).get('candidate_release_tag') or '') != str(seal.get('candidate_release_tag') or '') or str((lab.get('source') or {}).get('candidate_readiness_sha256') or '') != str(readiness.get('readiness_sha256') or ''):
                    raise TournamentContractError('immutable decision lab exists for different candidate evidence')
                existing.append(tag)
                continue
            deadline = _parse_utc(str(seal.get('deadline') or ''))
            if now >= deadline:
                skipped_postdeadline.append(str(seal.get('candidate_release_tag') or ''))
                continue
            manager_attempt, surfaces, hashes, public_files = _load_candidate_context(public_store=public_store, private_store=private_store, public_releases=public_releases, private_releases=private_releases, candidate_release=release, readiness=readiness, root=root / f'context-{run_id}')
            lab = build_decision_lab(readiness=readiness, private_attempt=manager_attempt, surfaces=surfaces, surface_hashes=hashes, public_files=public_files, control_plane_sha=control_plane_sha)
            _write_private_release(private_store=private_store, tag=tag, payload=lab, payload_name='decision_lab.json', attestation_name='decision_lab_attestation.json', scope='PRIVATE_PROSPECTIVE_DECISION_LAB', workdir=root / f'new-lab-{run_id}', title=f"Apex V2 private prospective decision lab {season} GW{readiness['target_gameweek']} {run_id}")
            sealed.append(tag)
            private_by_tag[tag] = {'tag_name': tag, 'immutable': True}
    return {'sealed': sealed, 'existing': existing, 'skipped_postdeadline': skipped_postdeadline, 'skipped_not_ready': skipped_not_ready, 'production_influence': 'NONE', 'serving_authorized': False}

def _position_counts_from_map(ids: Iterable[int], positions: dict[int, str]) -> dict[str, int]:
    counts = {'GK': 0, 'DEF': 0, 'MID': 0, 'FWD': 0}
    for player_id in ids:
        position = str(positions.get(int(player_id)) or '')
        if position not in counts:
            raise TournamentContractError(f'decision-edge score lacks Official position for element {player_id}')
        counts[position] += 1
    return counts

def _legal_nominal_xi(ids: Iterable[int], positions: dict[int, str]) -> bool:
    values = tuple((int(value) for value in ids))
    if len(values) != 11 or len(set(values)) != 11:
        return False
    counts = _position_counts_from_map(values, positions)
    return counts['GK'] == 1 and XI_MIN[Position.DEF] <= counts['DEF'] <= XI_MAX[Position.DEF] and (XI_MIN[Position.MID] <= counts['MID'] <= XI_MAX[Position.MID]) and (XI_MIN[Position.FWD] <= counts['FWD'] <= XI_MAX[Position.FWD])

def _resolve_outfield_autosubs(*, xi_ids: tuple[int, ...], bench_order: tuple[int, ...], minutes: dict[int, float], positions: dict[int, str]) -> tuple[int, ...]:
    missing = tuple((player_id for player_id in xi_ids if positions[player_id] != 'GK' and minutes.get(player_id, 0.0) <= 0))
    outfield_bench = tuple((player_id for player_id in bench_order if positions[player_id] != 'GK'))
    if not missing:
        return ()
    initial_counts = _position_counts_from_map(xi_ids, positions)
    def recurse(index: int, remaining: tuple[int, ...], counts: dict[str, int]) -> tuple[tuple[int, ...], tuple[int, ...]]:
        if index >= len(outfield_bench) or not remaining:
            return ((), ())
        bench_id = outfield_bench[index]
        if minutes.get(bench_id, 0.0) <= 0:
            return recurse(index + 1, remaining, counts)
        legal_replacements: list[int] = []
        for missing_id in remaining:
            old_position = positions[missing_id]
            new_position = positions[bench_id]
            trial = dict(counts)
            trial[old_position] -= 1
            trial[new_position] += 1
            if XI_MIN[Position.DEF] <= trial['DEF'] <= XI_MAX[Position.DEF] and XI_MIN[Position.MID] <= trial['MID'] <= XI_MAX[Position.MID] and (XI_MIN[Position.FWD] <= trial['FWD'] <= XI_MAX[Position.FWD]):
                legal_replacements.append(missing_id)
        if not legal_replacements:
            return recurse(index + 1, remaining, counts)
        candidates = []
        for missing_id in sorted(legal_replacements):
            old_position = positions[missing_id]
            new_position = positions[bench_id]
            trial = dict(counts)
            trial[old_position] -= 1
            trial[new_position] += 1
            next_remaining = tuple((value for value in remaining if value != missing_id))
            later_used, later_replaced = recurse(index + 1, next_remaining, trial)
            candidates.append(((bench_id, *later_used), (missing_id, *later_replaced)))
        return min(candidates, key=lambda row: (-len(row[0]), row[1], row[0]))
    used, _ = recurse(0, missing, initial_counts)
    return tuple(used)

def _realized_decision_score(decision: dict[str, Any], *, actual_points: dict[int, float], actual_minutes: dict[int, float], positions: dict[int, str], active_chip: str | None, transfer_hit_cost: int) -> dict[str, Any]:
    squad = tuple((int(value) for value in decision.get('squad_ids') or []))
    xi = tuple((int(value) for value in decision.get('xi_ids') or []))
    bench = tuple((int(value) for value in decision.get('bench_order') or []))
    if len(squad) != 15 or len(set(squad)) != 15:
        raise TournamentContractError('decision-edge variant lacks exact 15-player squad')
    if len(xi) != 11 or len(bench) != 4:
        raise TournamentContractError('decision-edge variant lacks exact XI/bench')
    if set(xi) | set(bench) != set(squad) or set(xi) & set(bench):
        raise TournamentContractError('decision-edge XI/bench do not partition squad')
    if not _legal_nominal_xi(xi, positions):
        raise TournamentContractError('decision-edge variant XI is not a legal formation')
    captain = int(decision['captain_id'])
    vice = int(decision['vice_captain_id'])
    if captain not in xi or vice not in xi or captain == vice:
        raise TournamentContractError('decision-edge captain/vice contract invalid')
    chip = str(active_chip or '').strip().lower()
    standard_chips = {'', 'none', 'freehit', 'free_hit', 'wildcard'}
    triple_chips = {'3xc', 'triple_captain', 'triplecaptain'}
    bench_boost_chips = {'bboost', 'bench_boost', 'benchboost'}
    if chip not in standard_chips | triple_chips | bench_boost_chips:
        raise TournamentContractError(f'decision-edge realized scoring does not recognize active chip {active_chip!r}')
    if chip in bench_boost_chips:
        scoring_ids = squad
        autosubs: tuple[int, ...] = ()
        goalkeeper_sub = None
    else:
        appeared_starters = [player_id for player_id in xi if actual_minutes.get(player_id, 0.0) > 0]
        starting_goalkeeper = next((player_id for player_id in xi if positions[player_id] == 'GK'))
        bench_goalkeeper = next((player_id for player_id in bench if positions[player_id] == 'GK'))
        goalkeeper_sub = None
        if actual_minutes.get(starting_goalkeeper, 0.0) <= 0 and actual_minutes.get(bench_goalkeeper, 0.0) > 0:
            goalkeeper_sub = bench_goalkeeper
        outfield_subs = _resolve_outfield_autosubs(xi_ids=xi, bench_order=bench, minutes=actual_minutes, positions=positions)
        autosubs = ((goalkeeper_sub,) if goalkeeper_sub is not None else ()) + outfield_subs
        scoring_ids = tuple(appeared_starters) + autosubs
    effective_captain = None
    if actual_minutes.get(captain, 0.0) > 0:
        effective_captain = captain
    elif actual_minutes.get(vice, 0.0) > 0:
        effective_captain = vice
    player_points = float(sum((actual_points.get(pid, 0.0) for pid in scoring_ids)))
    captain_copy_count = 2 if chip in triple_chips else 1
    captain_bonus = captain_copy_count * float(actual_points.get(effective_captain, 0.0)) if effective_captain is not None else 0.0
    hits = int(decision.get('transfer_hits') or 0)
    if hits < 0:
        raise TournamentContractError('decision-edge transfer hit count cannot be negative')
    hit_cost = float(hits * int(transfer_hit_cost))
    total = player_points + captain_bonus - hit_cost
    return {'realized_points_after_hits': float(total), 'player_points_before_captain_and_hits': player_points, 'effective_captain_id': effective_captain, 'captain_bonus_points': float(captain_bonus), 'transfer_hits': hits, 'transfer_hit_cost_points': hit_cost, 'autosubbed_in_ids': list(autosubs), 'goalkeeper_autosub_id': goalkeeper_sub, 'scoring_player_count_before_captain': len(scoring_ids), 'active_chip': active_chip}

def _load_outcome(*, public_store: Any, release: dict[str, Any], workdir: Path) -> tuple[dict[str, Any], str]:
    if release.get('immutable') is not True:
        raise TournamentContractError('decision-edge outcome release is mutable')
    if frozenset(_release_asset_map(release)) != frozenset({'outcomes.json'}):
        raise TournamentContractError('decision-edge outcome asset contract mismatch')
    files = _download_release_files(public_store, release, {'outcomes.json'}, workdir)
    return (_load_json(files['outcomes.json']), sha256_path(files['outcomes.json']))

def _validated_control_plane_sha(value: Any, *, context: str) -> str:
    sha = str(value or '').strip().lower()
    if len(sha) != 40 or any((char not in '0123456789abcdef' for char in sha)):
        raise TournamentContractError(f'{context} lacks valid decision-lab control-plane identity')
    return sha

def build_decision_edge(*, lab: dict[str, Any], outcome: dict[str, Any], observation_number: int, selected_candidate_tag: str, outcome_sha256: str) -> dict[str, Any]:
    if lab.get('contract') != LAB_CONTRACT:
        raise TournamentContractError('decision-edge source lab contract mismatch')
    lab_control_plane_sha = _validated_control_plane_sha(lab.get('control_plane_sha'), context='decision-edge source lab')
    source = lab.get('source') or {}
    if str(source.get('candidate_release_tag') or '') != str(selected_candidate_tag):
        raise TournamentContractError('decision-edge lab is not bound to canonical selected candidate')
    gameweek = int(source.get('target_gameweek') or 0)
    if int(outcome.get('gameweek') or -1) != gameweek:
        raise TournamentContractError('decision-edge outcome Gameweek mismatch')
    if str(outcome.get('public_attempt_id') or '') != str(source.get('public_attempt_id') or ''):
        raise TournamentContractError('decision-edge outcome identity mismatch')
    actual_points = {int(key): float(value) for key, value in (outcome.get('actual_points') or {}).items()}
    actual_minutes = {int(key): float(value) for key, value in (outcome.get('actual_minutes') or {}).items()}
    if not actual_points or not actual_minutes:
        raise TournamentContractError('decision-edge outcome lacks complete score maps')
    positions = {int(key): str(value) for key, value in (lab.get('private_position_map') or {}).items()}
    rules = season_rules(str(source.get('season') or ''))
    active_chip = (lab.get('team_context') or {}).get('active_chip')
    variants = lab.get('variants') or {}
    baseline_id = str(lab.get('baseline_variant_id') or '')
    baseline_variant = variants.get(baseline_id)
    if not isinstance(baseline_variant, dict):
        raise TournamentContractError('decision-edge source has no baseline variant')
    scored: dict[str, Any] = {}
    for variant_id, variant in sorted(variants.items()):
        decision = variant.get('decision')
        if not isinstance(decision, dict):
            raise TournamentContractError(f'decision-edge variant lacks sealed decision: {variant_id}')
        result = _realized_decision_score(decision, actual_points=actual_points, actual_minutes=actual_minutes, positions=positions, active_chip=active_chip, transfer_hit_cost=rules.transfer_hit_cost)
        scored[variant_id] = {'variant_id': variant_id, 'variant_kind': variant.get('variant_kind'), 'provider_id': variant.get('provider_id'), 'decision_signature_sha256': variant.get('decision_signature_sha256'), 'realized': result}
    baseline_points = float(scored[baseline_id]['realized']['realized_points_after_hits'])
    baseline_signature = str(scored[baseline_id].get('decision_signature_sha256') or '')
    for variant_id, row in scored.items():
        realized = float(row['realized']['realized_points_after_hits'])
        row['edge_vs_production_points'] = realized - baseline_points
        row['decision_changed_vs_production'] = str(row.get('decision_signature_sha256') or '') != baseline_signature
    return {'schema_version': 1, 'contract': PRIVATE_EDGE_CONTRACT, 'exposure_class': 'PRIVATE_MANAGER', 'production_influence': 'NONE', 'serving_authorized': False, 'promotion_authority': False, 'automatic_serving_change': False, 'retrospective_only_over_prospectively_sealed_variants': True, 'source': {'season': source.get('season'), 'target_gameweek': gameweek, 'run_id': source.get('run_id'), 'public_attempt_id': source.get('public_attempt_id'), 'prospective_observation_number': int(observation_number), 'selected_candidate_tag': selected_candidate_tag, 'candidate_readiness_sha256': source.get('candidate_readiness_sha256'), 'decision_lab_sha256': canonical_sha256(lab), 'decision_lab_control_plane_sha': lab_control_plane_sha, 'outcome_sha256': outcome_sha256, 'official_live_hash': outcome.get('official_live_hash')}, 'active_chip': active_chip, 'baseline_variant_id': baseline_id, 'baseline_realized_points_after_hits': baseline_points, 'variants': scored}

def score_completed_labs(*, public_store: Any, private_store: Any, season: str) -> dict[str, Any]:
    public_releases = public_store.list_releases()
    private_releases = private_store.list_releases()
    public_by_tag = {str(row.get('tag_name') or ''): row for row in public_releases if not row.get('draft')}
    private_by_tag = {str(row.get('tag_name') or ''): row for row in private_releases if not row.get('draft')}
    published: list[str] = []
    existing: list[str] = []
    missing_lab: list[str] = []
    awaiting_outcome: list[str] = []
    selections = [release for release in public_releases if str(release.get('tag_name') or '').startswith(f'{SELECTION_PREFIX}/{season}/') and (not release.get('draft')) and (release.get('immutable') is True)]
    with tempfile.TemporaryDirectory(prefix='apex-decision-edge-') as tmp:
        root = Path(tmp)
        seen_observations: set[int] = set()
        for release in selections:
            selection = _load_selection(public_store, release, root / f"selection-{release['id']}")
            observation = int(selection['prospective_observation_number'])
            if observation in seen_observations:
                raise TournamentContractError(f'duplicate decision-edge canonical observation {observation}')
            seen_observations.add(observation)
            candidate_tag = str(selection['selected_candidate_tag'])
            candidate_release = public_by_tag.get(candidate_tag)
            if candidate_release is None:
                raise TournamentContractError('decision-edge canonical candidate release is missing')
            readiness = _download_candidate(public_store, candidate_release, root / f'selected-candidate-{observation}')
            run_id = str((readiness.get('common_seal') or {}).get('run_id') or '')
            lab_tag = f'{LAB_PREFIX}/{season}/{run_id}'
            lab_release = private_by_tag.get(lab_tag)
            if lab_release is None:
                missing_lab.append(candidate_tag)
                continue
            outcome_tag = f'apex-v2/outcome/{season}/{run_id}'
            outcome_release = public_by_tag.get(outcome_tag)
            if outcome_release is None:
                awaiting_outcome.append(outcome_tag)
                continue
            edge_tag = f'{PRIVATE_EDGE_PREFIX}/{season}/obs{observation}'
            prior = private_by_tag.get(edge_tag)
            if prior is not None:
                _load_private_payload(store=private_store, release=prior, payload_name='decision_edge.json', attestation_name='decision_edge_attestation.json', expected_assets=PRIVATE_EDGE_ASSETS, scope='PRIVATE_PROSPECTIVE_DECISION_EDGE', workdir=root / f'existing-edge-{observation}')
                existing.append(edge_tag)
                continue
            lab = _load_private_payload(store=private_store, release=lab_release, payload_name='decision_lab.json', attestation_name='decision_lab_attestation.json', expected_assets=LAB_ASSETS, scope='PRIVATE_PROSPECTIVE_DECISION_LAB', workdir=root / f'lab-{observation}')
            outcome, outcome_sha = _load_outcome(public_store=public_store, release=outcome_release, workdir=root / f'outcome-{observation}')
            edge = build_decision_edge(lab=lab, outcome=outcome, observation_number=observation, selected_candidate_tag=candidate_tag, outcome_sha256=outcome_sha)
            _write_private_release(private_store=private_store, tag=edge_tag, payload=edge, payload_name='decision_edge.json', attestation_name='decision_edge_attestation.json', scope='PRIVATE_PROSPECTIVE_DECISION_EDGE', workdir=root / f'new-edge-{observation}', title=f'Apex V2 private decision edge {season} observation {observation}')
            private_by_tag[edge_tag] = {'tag_name': edge_tag, 'immutable': True}
            published.append(edge_tag)
    return {'published': published, 'existing': existing, 'missing_predeadline_lab': missing_lab, 'awaiting_outcome': awaiting_outcome, 'production_influence': 'NONE', 'serving_authorized': False}
EDGE_STAGE_RANK = {'INSUFFICIENT_COMPARISON': 0, 'DIAGNOSTIC_SIGNAL': 1, 'MIXED_EVIDENCE': 2, 'EMERGING_EDGE': 3, 'FAST_TRACK_REVIEW_ELIGIBLE': 4, 'ACTIONABLE_SPECIALIST_REVIEW': 5, 'SPECIALIST_ROLE_CANDIDATE': 6, 'STRONG_EVIDENCE': 7, 'MATURE_EVIDENCE': 8}
EDGE_REVIEW_STAGES = frozenset({'FAST_TRACK_REVIEW_ELIGIBLE', 'ACTIONABLE_SPECIALIST_REVIEW', 'SPECIALIST_ROLE_CANDIDATE', 'STRONG_EVIDENCE', 'MATURE_EVIDENCE'})

def _edge_stage(*, observations: int, positive_rate: float, mean_edge: float, worst_edge: float) -> str:
    if observations <= 0:
        return 'INSUFFICIENT_COMPARISON'
    if observations == 1:
        return 'DIAGNOSTIC_SIGNAL'
    if observations >= 12 and positive_rate >= 0.7 and (mean_edge >= 1.0) and (worst_edge >= -3.0):
        return 'MATURE_EVIDENCE'
    if observations >= 8 and positive_rate >= 0.7 and (mean_edge >= 1.5) and (worst_edge >= -3.0):
        return 'STRONG_EVIDENCE'
    if observations >= 5 and positive_rate >= 0.7 and (mean_edge >= 2.0) and (worst_edge >= -3.0):
        return 'SPECIALIST_ROLE_CANDIDATE'
    if observations >= 3 and positive_rate >= 2.0 / 3.0 and (mean_edge >= 1.5) and (worst_edge >= -4.0):
        return 'ACTIONABLE_SPECIALIST_REVIEW'
    if observations == 2 and positive_rate == 1.0 and (mean_edge >= LARGE_EDGE_POINTS):
        return 'FAST_TRACK_REVIEW_ELIGIBLE'
    if observations >= 2 and positive_rate >= 2.0 / 3.0 and (mean_edge >= 1.0):
        return 'EMERGING_EDGE'
    return 'MIXED_EVIDENCE'

def build_decision_edge_learning(edges: Iterable[dict[str, Any]], *, season: str) -> dict[str, Any]:
    edge_rows = sorted(list(edges), key=lambda row: int((row.get('source') or {}).get('prospective_observation_number') or 0))
    observations = [int((row.get('source') or {})['prospective_observation_number']) for row in edge_rows]
    if len(observations) != len(set(observations)):
        raise TournamentContractError('decision-edge learning has duplicate observations')
    max_observation = max(observations, default=0)
    series: dict[tuple[str, str], list[dict[str, Any]]] = {}
    control_planes_by_variant: dict[str, set[str]] = {}
    for edge in edge_rows:
        source = edge.get('source') or {}
        observation = int(source['prospective_observation_number'])
        control_plane_sha = _validated_control_plane_sha(source.get('decision_lab_control_plane_sha'), context=f'decision-edge observation {observation}')
        for variant_id, row in (edge.get('variants') or {}).items():
            if variant_id == edge.get('baseline_variant_id'):
                continue
            variant_id = str(variant_id)
            control_planes_by_variant.setdefault(variant_id, set()).add(control_plane_sha)
            key = (variant_id, control_plane_sha)
            series.setdefault(key, []).append({'observation_number': observation, 'target_gameweek': int(source['target_gameweek']), 'provider_id': str(row.get('provider_id') or ''), 'variant_kind': str(row.get('variant_kind') or ''), 'edge_points': float(row.get('edge_vs_production_points') or 0.0), 'decision_changed': bool(row.get('decision_changed_vs_production')), 'decision_lab_control_plane_sha': control_plane_sha})
    variants: dict[str, Any] = {}
    provider_summary: dict[str, Any] = {}
    review_queue: list[dict[str, Any]] = []
    for (variant_id, control_plane_sha), rows in sorted(series.items()):
        latest_observation = max((row['observation_number'] for row in rows))
        weights = [0.5 ** ((latest_observation - row['observation_number']) / RECENCY_HALF_LIFE_OBSERVATIONS) for row in rows]
        denominator = sum(weights)
        weighted_edge = sum((weight * row['edge_points'] for weight, row in zip(weights, rows))) / denominator
        positive_rate = sum((weight for weight, row in zip(weights, rows) if row['edge_points'] > 1e-12)) / denominator
        worst = min((row['edge_points'] for row in rows))
        changed = [row for row in rows if row['decision_changed']]
        changed_rate = len(changed) / len(rows)
        provider_id = rows[-1]['provider_id']
        variant_kind = rows[-1]['variant_kind']
        if any((row['provider_id'] != provider_id for row in rows)):
            raise TournamentContractError(f'decision-edge variant provider identity drift: {variant_id}')
        cohort_id = variant_id if len(control_planes_by_variant[variant_id]) == 1 else f'{variant_id}@@{control_plane_sha[:12]}'
        stage = _edge_stage(observations=len(rows), positive_rate=positive_rate, mean_edge=weighted_edge, worst_edge=worst)
        summary = {'variant_id': variant_id, 'evidence_cohort_id': cohort_id, 'decision_lab_control_plane_sha': control_plane_sha, 'provider_id': provider_id, 'variant_kind': variant_kind, 'observation_count': len(rows), 'observation_numbers': [row['observation_number'] for row in rows], 'recency_weighted_mean_edge_points': weighted_edge, 'recency_weighted_positive_edge_rate': positive_rate, 'worst_edge_points': worst, 'best_edge_points': max((row['edge_points'] for row in rows)), 'decision_changed_observations': len(changed), 'decision_changed_rate': changed_rate, 'stage': stage, 'review_eligible': stage in EDGE_REVIEW_STAGES, 'serving_change_authorized': False}
        variants[cohort_id] = summary
        provider = provider_summary.setdefault(provider_id, {'variant_ids': [], 'evidence_cohort_ids': [], 'review_eligible_variant_ids': [], 'review_eligible_evidence_cohort_ids': [], 'best_weighted_edge_points': None})
        if variant_id not in provider['variant_ids']:
            provider['variant_ids'].append(variant_id)
        provider['evidence_cohort_ids'].append(cohort_id)
        if summary['review_eligible']:
            if variant_id not in provider['review_eligible_variant_ids']:
                provider['review_eligible_variant_ids'].append(variant_id)
            provider['review_eligible_evidence_cohort_ids'].append(cohort_id)
            review_queue.append({'provider_id': provider_id, 'variant_id': variant_id, 'evidence_cohort_id': cohort_id, 'decision_lab_control_plane_sha': control_plane_sha, 'variant_kind': variant_kind, 'stage': stage, 'observations': len(rows), 'recency_weighted_mean_edge_points': weighted_edge, 'serving_change_authorized': False})
        best = provider['best_weighted_edge_points']
        provider['best_weighted_edge_points'] = weighted_edge if best is None else max(float(best), weighted_edge)
    review_queue.sort(key=lambda row: (-EDGE_STAGE_RANK[row['stage']], -float(row['recency_weighted_mean_edge_points']), row['provider_id'], row['variant_id'], row['evidence_cohort_id']))
    return {'schema_version': 1, 'contract': PRIVATE_EDGE_LEARNING_CONTRACT, 'exposure_class': 'PRIVATE_MANAGER', 'season': season, 'production_influence': 'NONE', 'serving_authorized': False, 'promotion_authority': False, 'automatic_serving_change': False, 'learning_mode': 'SEQUENTIAL_EVERY_COMPLETED_CANONICAL_H1', 'evidence_cohorting': 'DECISION_LAB_CONTROL_PLANE_SHA', 'cross_control_plane_pooling': False, 'twelve_gameweeks_required_before_learning': False, 'twelve_gameweeks_required_before_review': False, 'recency_half_life_observations': RECENCY_HALF_LIFE_OBSERVATIONS, 'completed_observation_count': len(observations), 'observation_numbers': observations, 'through_observation': max_observation or None, 'variant_evidence': variants, 'provider_summary': provider_summary, 'owner_review_queue': review_queue, 'serving_action': 'NO_AUTOMATIC_CHANGE'}
PRIVATE_EDGE_LEARNING_PREFIX = 'apex-v2/private-decision-edge-learning'
PRIVATE_EDGE_LEARNING_ASSETS = frozenset({'decision_edge_learning.json', 'decision_edge_learning_attestation.json'})

def publish_decision_edge_learning(*, private_store: Any, season: str) -> dict[str, Any]:
    releases = private_store.list_releases()
    edge_releases = [release for release in releases if str(release.get('tag_name') or '').startswith(f'{PRIVATE_EDGE_PREFIX}/{season}/obs') and (not release.get('draft')) and (release.get('immutable') is True)]
    edges: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix='apex-decision-edge-learning-') as tmp:
        root = Path(tmp)
        for release in edge_releases:
            edges.append(_load_private_payload(store=private_store, release=release, payload_name='decision_edge.json', attestation_name='decision_edge_attestation.json', expected_assets=PRIVATE_EDGE_ASSETS, scope='PRIVATE_PROSPECTIVE_DECISION_EDGE', workdir=root / f"edge-{release['id']}"))
        report = build_decision_edge_learning(edges, season=season)
        through = report.get('through_observation')
        if through is None:
            return report
        tag = f'{PRIVATE_EDGE_LEARNING_PREFIX}/{season}/through-obs{through}'
        existing = _find_release(releases, tag)
        if existing is not None:
            observed = _load_private_payload(store=private_store, release=existing, payload_name='decision_edge_learning.json', attestation_name='decision_edge_learning_attestation.json', expected_assets=PRIVATE_EDGE_LEARNING_ASSETS, scope='PRIVATE_DECISION_EDGE_LEARNING', workdir=root / 'existing-learning')
            if observed != report:
                raise TournamentContractError('immutable decision-edge learning snapshot differs from evidence')
            return observed
        _write_private_release(private_store=private_store, tag=tag, payload=report, payload_name='decision_edge_learning.json', attestation_name='decision_edge_learning_attestation.json', scope='PRIVATE_DECISION_EDGE_LEARNING', workdir=root / 'new-learning', title=f'Apex V2 private decision-edge learning through observation {through}')
        return report
PUBLIC_OUTCOME_PREFIX = 'apex-v2/outcome'
PRIVATE_MANAGER_PREFIX = 'apex-v2/private'
PRIVATE_DQ_PREFIX = 'apex-v2/private-decision-quality'
DQ_ASSETS = frozenset({'decision_quality.json', 'decision_quality_attestation.json'})

def canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')

def _int_map(raw: Any) -> dict[int, float]:
    if not isinstance(raw, dict):
        return {}
    output: dict[int, float] = {}
    for key, value in raw.items():
        try:
            output[int(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return output

def _int_list(raw: Any) -> list[int]:
    if not isinstance(raw, (list, tuple)):
        return []
    output: list[int] = []
    for value in raw:
        try:
            output.append(int(value))
        except (TypeError, ValueError):
            continue
    return output

def _official_players(private_attempt: dict[str, Any]) -> dict[int, dict[str, Any]]:
    rows = ((private_attempt.get('canonical_forecast') or {}).get('official') or {}).get('players') or []
    players: dict[int, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            players[int(row['element_id'])] = row
        except (KeyError, TypeError, ValueError):
            continue
    return players

def _position_counts(ids: tuple[int, ...], players: dict[int, dict[str, Any]]) -> dict[str, int]:
    counts = {'GK': 0, 'DEF': 0, 'MID': 0, 'FWD': 0}
    for pid in ids:
        position = str((players.get(pid) or {}).get('position') or '')
        if position not in counts:
            raise RuntimeError(f'missing/invalid Official position for element {pid}')
        counts[position] += 1
    return counts

def legal_xi(ids: tuple[int, ...], players: dict[int, dict[str, Any]]) -> bool:
    if len(ids) != 11 or len(set(ids)) != 11:
        return False
    counts = _position_counts(ids, players)
    return counts['GK'] == 1 and 3 <= counts['DEF'] <= 5 and (2 <= counts['MID'] <= 5) and (1 <= counts['FWD'] <= 3)

def best_legal_xi(squad_ids: list[int], actual_points: dict[int, float], players: dict[int, dict[str, Any]]) -> tuple[list[int], float]:
    import itertools
    if len(squad_ids) != 15 or len(set(squad_ids)) != 15:
        raise RuntimeError('decision quality requires an exact 15-player final squad')
    missing = [pid for pid in squad_ids if pid not in players]
    if missing:
        raise RuntimeError('Official player catalog does not cover final squad')
    best_ids: tuple[int, ...] | None = None
    best_points: float | None = None
    for combo in itertools.combinations(squad_ids, 11):
        if not legal_xi(combo, players):
            continue
        points = float(sum((actual_points.get(pid, 0.0) for pid in combo)))
        if best_points is None or points > best_points or (points == best_points and combo < (best_ids or combo)):
            best_ids = combo
            best_points = points
    if best_ids is None or best_points is None:
        raise RuntimeError('final squad contains no legal FPL XI')
    return (list(best_ids), best_points)

def _h1_expected_minutes(private_attempt: dict[str, Any]) -> dict[int, float]:
    forecast = private_attempt.get('canonical_forecast') or {}
    gameweek = int(private_attempt.get('target_gameweek') or 0)
    serving = forecast.get('serving_provider_by_horizon') or {}
    champion = str(serving.get('1', serving.get(1, '')) or '')
    output: dict[int, float] = {}
    for row in forecast.get('rows') or []:
        if not isinstance(row, dict):
            continue
        try:
            if int(row.get('gameweek', -1)) != gameweek or int(row.get('horizon', -1)) != 1:
                continue
            if champion and str(row.get('serving_provider_id') or '') != champion:
                continue
            if row.get('expected_minutes') is None:
                continue
            output[int(row['element_id'])] = float(row['expected_minutes'])
        except (KeyError, TypeError, ValueError):
            continue
    return output

def build_decision_quality(private_attempt: dict[str, Any], outcome: dict[str, Any], *, source_private_sha256: str, source_outcome_sha256: str, control_plane_sha: str) -> dict[str, Any]:
    public_id = str(private_attempt.get('public_attempt_id') or '')
    if not public_id or str(outcome.get('public_attempt_id') or '') != public_id:
        raise RuntimeError('decision-quality public/private identity mismatch')
    gameweek = int(private_attempt.get('target_gameweek') or 0)
    if gameweek <= 0 or int(outcome.get('gameweek') or -1) != gameweek:
        raise RuntimeError('decision-quality Gameweek mismatch')
    system = private_attempt.get('system_decision')
    if not isinstance(system, dict):
        raise RuntimeError('decision-quality source has no system decision')
    actual = _int_map(outcome.get('actual_points'))
    minutes = _int_map(outcome.get('actual_minutes'))
    if not actual or not minutes:
        raise RuntimeError('decision-quality outcome has no scoreable actuals')
    squad_ids = _int_list(system.get('squad_ids'))
    xi_ids = _int_list(system.get('xi_ids'))
    bench_ids = _int_list(system.get('bench_order'))
    if len(xi_ids) != 11 or len(bench_ids) != 4:
        raise RuntimeError('decision-quality requires exact XI and four-player bench')
    if set(xi_ids) | set(bench_ids) != set(squad_ids):
        raise RuntimeError('decision-quality XI/bench do not partition final squad')
    players = _official_players(private_attempt)
    if not legal_xi(tuple(xi_ids), players):
        raise RuntimeError('sealed selected XI is not a legal formation')
    best_ids, best_points = best_legal_xi(squad_ids, actual, players)
    selected_points = float(sum((actual.get(pid, 0.0) for pid in xi_ids)))
    bench_points = float(sum((actual.get(pid, 0.0) for pid in bench_ids)))
    captain_id = int(system.get('captain_id'))
    vice_id = int(system.get('vice_captain_id'))
    if captain_id not in squad_ids or vice_id not in squad_ids:
        raise RuntimeError('captain or vice-captain is outside final squad')
    if minutes.get(captain_id, 0.0) > 0:
        effective_captain = captain_id
    elif minutes.get(vice_id, 0.0) > 0:
        effective_captain = vice_id
    else:
        effective_captain = None
    effective_bonus = float(actual.get(effective_captain, 0.0)) if effective_captain is not None else 0.0
    available_xi = [pid for pid in xi_ids if minutes.get(pid, 0.0) > 0]
    best_captain = max(available_xi, key=lambda pid: (actual.get(pid, 0.0), -pid)) if available_xi else None
    best_bonus = float(actual.get(best_captain, 0.0)) if best_captain is not None else 0.0
    transfers_in = _int_list(system.get('transfers_in'))
    transfers_out = _int_list(system.get('transfers_out'))
    incoming_points = float(sum((actual.get(pid, 0.0) for pid in transfers_in)))
    outgoing_points = float(sum((actual.get(pid, 0.0) for pid in transfers_out)))
    transfer_delta = incoming_points - outgoing_points if len(transfers_in) == len(transfers_out) else None
    expected_minutes = _h1_expected_minutes(private_attempt)
    minute_rows = [pid for pid in squad_ids if pid in expected_minutes and pid in minutes]
    minute_mae = float(sum((abs(expected_minutes[pid] - minutes[pid]) for pid in minute_rows)) / len(minute_rows)) if minute_rows else None
    team_state = private_attempt.get('team_state') or {}
    return {'schema_version': 1, 'contract': 'APEX_V2_PRIVATE_DECISION_QUALITY_V1', 'production_influence': 'NONE', 'serving_authorized': False, 'promotion_authority': False, 'source': {'season': private_attempt.get('season'), 'gameweek': gameweek, 'public_attempt_id': public_id, 'private_attempt_id': private_attempt.get('private_attempt_id'), 'private_manager_sha256': source_private_sha256, 'outcomes_sha256': source_outcome_sha256, 'official_live_hash': outcome.get('official_live_hash'), 'canonical_projection_sha256': (private_attempt.get('canonical_forecast') or {}).get('canonical_projection_sha256'), 'control_plane_sha': control_plane_sha}, 'captaincy': {'sealed_captain_id': captain_id, 'sealed_vice_captain_id': vice_id, 'effective_captain_id': effective_captain, 'effective_captain_bonus_points': effective_bonus, 'best_realized_captain_id_within_sealed_xi': best_captain, 'best_realized_captain_bonus_points_within_sealed_xi': best_bonus, 'captain_bonus_realized_regret': max(0.0, best_bonus - effective_bonus)}, 'lineup': {'selected_xi_points_pre_autosub': selected_points, 'best_legal_xi_points_within_final_15': best_points, 'starting_xi_realized_regret_pre_autosub': max(0.0, best_points - selected_points), 'best_legal_xi_ids_within_final_15': best_ids, 'bench_realized_points': bench_points, 'zero_minute_selected_starters': [pid for pid in xi_ids if minutes.get(pid, 0.0) <= 0], 'bench_players_with_minutes': [pid for pid in bench_ids if minutes.get(pid, 0.0) > 0]}, 'transfers': {'free_transfers_before': team_state.get('free_transfers'), 'rolled_or_held': not transfers_in and (not transfers_out), 'transfers_in': transfers_in, 'transfers_out': transfers_out, 'same_gameweek_incoming_points': incoming_points, 'same_gameweek_outgoing_points': outgoing_points, 'same_gameweek_transferred_player_points_delta_vs_hold': transfer_delta, 'transfer_hits_recorded': int(system.get('transfer_hits') or 0), 'hit_cost_interpreted': False}, 'minutes': {'final_squad_expected_minutes_rows': len(minute_rows), 'final_squad_expected_minutes_coverage': len(minute_rows) / len(squad_ids) if squad_ids else 0.0, 'final_squad_expected_minutes_mae': minute_mae}, 'notes': ['All metrics are retrospective observational diagnostics over a prospectively sealed decision and immutable post-Gameweek outcome.', 'Captain regret is conditional on the sealed XI; lineup regret is separately measured as pre-autosub hindsight within the owned final 15.', 'Transferred-player delta is same-Gameweek incoming minus outgoing realized points only; it is not total team regret and future value/hit cost are deliberately not inferred here.', 'These diagnostics cannot alter serving-provider authority or production decisions.']}

def publish_completed_decision_quality(*, public_store: Any, private_store: Any, season: str, control_plane_sha: str) -> list[str]:
    from apex.runtime.publication import PRIVATE_RELEASE_ASSETS_V1
    from apex.runtime.releases import download_release_asset, release_asset_map
    public_releases = public_store.list_releases()
    private_releases = private_store.list_releases()
    private_by_tag = {str(row.get('tag_name')): row for row in private_releases if not row.get('draft')}
    published: list[str] = []
    outcome_prefix = f'{PUBLIC_OUTCOME_PREFIX}/{season}/'
    outcomes = [row for row in public_releases if str(row.get('tag_name') or '').startswith(outcome_prefix) and (not row.get('draft'))]
    for outcome_release in sorted(outcomes, key=lambda row: str(row.get('published_at') or '')):
        if not bool(outcome_release.get('immutable', False)):
            raise RuntimeError('decision-quality outcome source is not immutable')
        run_id = str(outcome_release['tag_name']).split(outcome_prefix, 1)[1]
        manager_tag = f'{PRIVATE_MANAGER_PREFIX}/{season}/{run_id}'
        dq_tag = f'{PRIVATE_DQ_PREFIX}/{season}/{run_id}'
        manager_release = private_by_tag.get(manager_tag)
        if manager_release is None:
            continue
        existing = private_by_tag.get(dq_tag)
        if existing is not None:
            if not bool(existing.get('immutable', False)):
                raise RuntimeError('existing decision-quality release is not immutable')
            if frozenset(release_asset_map(existing)) != DQ_ASSETS:
                raise RuntimeError('existing decision-quality release asset contract mismatch')
            continue
        if not bool(manager_release.get('immutable', False)):
            raise RuntimeError('decision-quality private source is not immutable')
        if frozenset(release_asset_map(outcome_release)) != frozenset({'outcomes.json'}):
            raise RuntimeError('outcome release asset contract mismatch')
        if frozenset(release_asset_map(manager_release)) != PRIVATE_RELEASE_ASSETS_V1:
            raise RuntimeError('private manager source asset contract mismatch')
        with tempfile.TemporaryDirectory(prefix='apex-decision-quality-') as tmp:
            root = Path(tmp)
            outcome_path = download_release_asset(public_store, outcome_release, 'outcomes.json', root / 'outcomes.json')
            manager_path = download_release_asset(private_store, manager_release, 'private_manager_attempt.json', root / 'private_manager_attempt.json')
            manager_attestation_path = download_release_asset(private_store, manager_release, 'private_attestation.json', root / 'private_attestation.json')
            outcome = json.loads(outcome_path.read_text(encoding='utf-8'))
            private_attempt = json.loads(manager_path.read_text(encoding='utf-8'))
            manager_attestation = json.loads(manager_attestation_path.read_text(encoding='utf-8'))
            manager_sha = sha256_path(manager_path)
            if manager_attestation.get('scope') != 'PRIVATE_MANAGER':
                raise RuntimeError('decision-quality private attestation scope mismatch')
            if manager_attestation.get('assets') != {'private_manager_attempt.json': manager_sha}:
                raise RuntimeError('decision-quality private attestation hash mismatch')
            if str(manager_attestation.get('public_attempt_id') or '') != str(outcome.get('public_attempt_id') or ''):
                raise RuntimeError('decision-quality source identity mismatch')
            dq = build_decision_quality(private_attempt, outcome, source_private_sha256=manager_sha, source_outcome_sha256=sha256_path(outcome_path), control_plane_sha=control_plane_sha)
            dq_path = root / 'decision_quality.json'
            dq_path.write_bytes(canonical_bytes(dq) + b'\n')
            attestation = {'schema_version': 1, 'contract': 'APEX_V2_PRIVATE_DECISION_QUALITY_ATTESTATION_V1', 'source_public_attempt_id': dq['source']['public_attempt_id'], 'source_private_manager_sha256': dq['source']['private_manager_sha256'], 'source_outcomes_sha256': dq['source']['outcomes_sha256'], 'assets': {'decision_quality.json': sha256_path(dq_path)}}
            attestation_path = root / 'decision_quality_attestation.json'
            attestation_path.write_bytes(canonical_bytes(attestation) + b'\n')
            ref = private_store.create_once(dq_tag, {'decision_quality.json': dq_path, 'decision_quality_attestation.json': attestation_path}, target_commitish=None, name=f"Apex V2 private decision quality {season} GW{dq['source']['gameweek']} {run_id}", body='Owner-private retrospective diagnostics over sealed Apex decisions. Non-serving; no promotion authority.')
            if not ref.immutable:
                raise RuntimeError('decision-quality release is not immutable')
            published.append(dq_tag)
    return published

def publish_completed(*, season: str, control_plane_sha: str) -> list[str]:
    """Backward-compatible entry point used by existing unit tests/operators."""
    from apex.runtime.releases import GitHubReleaseStore
    public_repo = os.environ.get('GITHUB_REPOSITORY', '').strip()
    public_token = os.environ.get('GITHUB_TOKEN', '').strip()
    private_repo = os.environ.get('APEX_PRIVATE_GITHUB_REPOSITORY', '').strip()
    private_token = os.environ.get('APEX_PRIVATE_GITHUB_TOKEN', '').strip()
    if not all((public_repo, public_token, private_repo, private_token)):
        raise RuntimeError('decision-quality scoring requires complete public/private store credentials')
    if public_repo == private_repo:
        raise RuntimeError('decision-quality private repository must be separate from public Apex')
    public_store = GitHubReleaseStore(public_repo, public_token)
    private_store = GitHubReleaseStore(private_repo, private_token)
    private_store.assert_repository_policy(require_private=True, require_immutable=True, require_initialized=True)
    return publish_completed_decision_quality(public_store=public_store, private_store=private_store, season=season, control_plane_sha=control_plane_sha)

def run_all(*, season: str, control_plane_sha: str) -> dict[str, Any]:
    from apex.runtime.releases import GitHubReleaseStore
    public_repo = os.environ.get('GITHUB_REPOSITORY', '').strip()
    public_token = os.environ.get('GITHUB_TOKEN', '').strip()
    private_repo = os.environ.get('APEX_PRIVATE_GITHUB_REPOSITORY', '').strip()
    private_token = os.environ.get('APEX_PRIVATE_GITHUB_TOKEN', '').strip()
    if not all((public_repo, public_token, private_repo, private_token)):
        raise RuntimeError('decision research requires complete public/private store credentials')
    if public_repo == private_repo:
        raise RuntimeError('decision research private repository must be separate from public Apex')
    public_store = GitHubReleaseStore(public_repo, public_token)
    private_store = GitHubReleaseStore(private_repo, private_token)
    private_store.assert_repository_policy(require_private=True, require_immutable=True, require_initialized=True)
    lab = seal_pending_labs(public_store=public_store, private_store=private_store, season=season, control_plane_sha=control_plane_sha)
    decision_quality = publish_completed_decision_quality(public_store=public_store, private_store=private_store, season=season, control_plane_sha=control_plane_sha)
    edge = score_completed_labs(public_store=public_store, private_store=private_store, season=season)
    learning = publish_decision_edge_learning(private_store=private_store, season=season)
    return {'schema_version': 1, 'contract': 'APEX_V2_DECISION_RESEARCH_CONTROLLER_V1', 'production_influence': 'NONE', 'serving_authorized': False, 'promotion_authority': False, 'automatic_serving_change': False, 'decision_lab': lab, 'decision_quality_published': decision_quality, 'decision_edge': edge, 'decision_edge_learning': {'through_observation': learning.get('through_observation'), 'owner_review_queue': learning.get('owner_review_queue') or []}}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--season', default='2026-2027')
    parser.add_argument('--control-plane-sha', required=True)
    args = parser.parse_args()
    result = run_all(season=args.season, control_plane_sha=args.control_plane_sha)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
