from __future__ import annotations
from pathlib import Path
import json, os
from apex.domain.models import *
from apex.forecast.registry import serving_policy, max_contiguous_qualified_horizon
from apex.forecast.contract import projection_surface_hash
from apex.decision.optimiser import optimise_initial_squad
from apex.decision.transfers import optimise_transfer_horizon
from apex.governance.certification import certify
from apex.governance.evidence import hard_exclusions
from .snapshot import open_frozen_snapshot
from .serde import official_from_dict, projection_from_dict, team_from_dict

def _status_from_row(row, surface):
    return ProviderStatus(row['provider_id'], ProviderRole(row['role']), int(row['priority']), ProviderHealth(row['health']), {int(k): Qualification(v) for k, v in row['qualification_by_horizon'].items()}, surface, tuple(row.get('reasons', [])), bool(row.get('serve_authorized', False)), Qualification(row.get('predictive_status', 'INSUFFICIENT_HISTORY')))

def _canonical(policy, max_h):
    rows = []
    ids = []
    versions = []
    first = None
    for h in range(1, max_h + 1):
        p = policy[h]
        first = first or p.surface
        ids.append(p.provider_id)
        versions.append(f'{p.provider_id}:{p.surface.provider_version}')
        rows.extend((r for r in p.surface.rows if r.horizon == h))
    return ProductionProjectionSurface(1, '|'.join(ids), '|'.join(versions), max((p.surface.generated_at for p in policy.values())), first.season, first.source_snapshot, first.scoring_rules_version, tuple(range(1, max_h + 1)), tuple(rows))

def solve_snapshot(snapshot_path: Path, output: Path) -> DecisionBundle:
    if os.getenv('APEX_ALLOW_NETWORK_DURING_SOLVE', '0') == '1':
        raise RuntimeError('network override is forbidden in production solve')
    snap = open_frozen_snapshot(snapshot_path)
    official = official_from_dict(snap.read_json('official.json'))
    team_raw = snap.read_json('team_state.json')
    team = team_from_dict(team_raw) if team_raw else None
    run = snap.read_json('run.json')
    matrix = snap.read_json('qualification_matrix.json')
    statuses = []
    for row in matrix:
        try:
            surface = projection_from_dict(snap.read_json(f"providers/{row['provider_id']}.json"))
        except (KeyError, FileNotFoundError):
            surface = None
        statuses.append(_status_from_row(row, surface))
    universe = official.decision_universe(set(team.squad_ids) if team else frozenset())
    policy = serving_policy(statuses, max_horizon=int(run['max_horizon']), decision_universe=universe)
    max_h = max_contiguous_qualified_horizon(policy)
    serving_h1 = policy.get(1)
    decision = None
    warnings = []
    evidence_rows = snap.read_json('evidence.json')
    records = tuple((EvidenceRecord(str(r['evidence_id']), int(r['element_id']), r['source_name'], r['source_url'], r['source_tier'], r['published_at'], r['retrieved_at'], r['expires_at'], r['evidence_type'], int(r['gameweek']), EvidenceEffect(r['effect']), r['content_hash'], r.get('excerpt', '')) for r in evidence_rows))
    excluded = hard_exclusions(records, int(run['target_gameweek']))
    if max_h >= 1:
        canonical = _canonical(policy, max_h)
        if team is None:
            result = optimise_initial_squad(official, canonical, horizon=1, excluded_ids=excluded)
            decision = result.decision
        else:
            tr = optimise_transfer_horizon(official, canonical, team, max_horizon=max_h, excluded_h1=excluded)
            decision = tr.decision
            warnings.extend([v for v in [tr.solver.get('reason')] if v])
        rows = {r.element_id: r for r in canonical.rows_for_horizon(1)}
        if decision and (not all((rows.get(pid) and rows[pid].p_appearance is not None for pid in decision.squad_ids))):
            warnings.append('appearance probabilities incomplete: contingent autosub/vice fallback EV is not included in primary objective')
        canonical_hash = projection_surface_hash(canonical)
    else:
        canonical_hash = ''
        warnings.append('no authorized complete H1 serving provider')
    for s in statuses:
        if s.role == ProviderRole.SHADOW and s.reasons:
            warnings.append(f"shadow {s.provider_id}: {'; '.join(s.reasons)}")
    evidence_errors = snap.read_json('evidence_validation.json').get('errors', [])
    cert = certify(official=official, serving=serving_h1, decision=decision, team_state=team, hard_evidence_conflict=bool(evidence_errors), degraded_warnings=tuple(warnings), valid_until=run['deadline'])
    manifest = RunManifest(1, run['run_id'], os.getenv('GITHUB_RUN_ID'), run['season'], int(run['target_gameweek']), run['code_sha'], run['config_sha'], run['acquired_at'], snap.snapshot_id, {h: p.provider_id for h, p in policy.items()}, run['run_started_at'], snap.manifest.get('metadata', {}).get('frozen_at', ''))
    bundle = DecisionBundle(1, manifest, official.source_hash, canonical_hash, decision, cert, {'statuses': matrix, 'max_contiguous_horizon': max_h, 'serving_provider_by_horizon': {str(h): p.provider_id for h, p in policy.items()}}, {'hard_evidence_count': len(records), 'validation_errors': evidence_errors})
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + '.tmp')
    tmp.write_text(json.dumps(dataclass_to_dict(bundle), indent=2, sort_keys=True, allow_nan=False) + '\n')
    os.replace(tmp, output)
    return bundle
