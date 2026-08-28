from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json
from apex.domain.models import ProviderHealth, ProviderStatus, Qualification, dataclass_to_dict, EvidenceRecord, EvidenceEffect
from apex.forecast.adapters.airsenal import load_airsenal
from apex.forecast.adapters.dastan import load_dastan
from apex.forecast.adapters.openfpl import load_openfpl
from apex.forecast.qualification import qualify_surface
from apex.sources.official import fetch_official_snapshot
from apex.sources.team import fetch_team_state
from apex.governance.evidence import validate_evidence
from .config import ApexConfig, config_sha
from .snapshot import SnapshotBuilder

def _parse_evidence(path: Path) -> tuple[EvidenceRecord, ...]:
    if not path.exists():
        return ()
    raw = json.loads(path.read_text())
    rows = raw if isinstance(raw, list) else raw.get('records', [])
    return tuple((EvidenceRecord(str(r['evidence_id']), int(r['element_id']), str(r['source_name']), str(r['source_url']), str(r['source_tier']), str(r['published_at']), str(r['retrieved_at']), str(r['expires_at']), str(r['evidence_type']), int(r['gameweek']), EvidenceEffect(r['effect']), str(r['content_hash']), str(r.get('excerpt', ''))) for r in rows))

def _target_gameweek(official, now):
    future = []
    for gw, val in official.deadlines.items():
        d = datetime.fromisoformat(val.replace('Z', '+00:00'))
        d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        if d > now:
            future.append(gw)
    if not future:
        raise RuntimeError('no future Official FPL deadline')
    return min(future)

def acquire_and_freeze(config_path: Path, *, run_id: str, code_sha: str, run_started_at: str, workdir: Path=Path('.')):
    config = ApexConfig.load(config_path)
    now = datetime.now(timezone.utc)
    official, raw_official = fetch_official_snapshot(season=config.season)
    target = _target_gameweek(official, now)
    team = fetch_team_state(config.entry_id, official, now=now)
    statuses = []
    normalized = {}
    start = datetime.fromisoformat(run_started_at.replace('Z', '+00:00'))
    start = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
    for pc in config.providers:
        path = workdir / pc.path
        surface = None
        reasons = []
        health = ProviderHealth.ERROR
        qh = {h: Qualification.UNQUALIFIED for h in pc.requested_horizons}
        if path.exists():
            try:
                if pc.provider_id == 'airsenal':
                    surface = load_airsenal(path, official=official, target_gameweek=target, trusted_source_snapshot=official.source_hash)
                elif pc.provider_id == 'dastan':
                    surface = load_dastan(path, official=official, target_gameweek=target)
                elif pc.provider_id == 'openfpl':
                    surface = load_openfpl(path, official=official, target_gameweek=target)
                else:
                    raise ValueError(f'unknown provider adapter {pc.provider_id}')
                generated = datetime.fromisoformat(surface.generated_at.replace('Z', '+00:00'))
                generated = generated if generated.tzinfo else generated.replace(tzinfo=timezone.utc)
                if generated < start:
                    reasons.append('provider forecast predates this production attempt')
                qr = qualify_surface(surface, official, decision_universe=official.decision_universe(team.squad_ids if team else frozenset()), requested_horizons=pc.requested_horizons, max_age_hours=pc.max_age_hours, now=now)
                reasons.extend(qr.reasons)
                health = qr.health
                for h in qr.qualified_horizons:
                    qh[h] = Qualification.QUALIFIED
                if reasons:
                    health = ProviderHealth.INCOMPLETE if health == ProviderHealth.HEALTHY else health
                normalized[pc.provider_id] = surface
            except Exception as exc:
                reasons.append(f'{type(exc).__name__}: {exc}')
                health = ProviderHealth.ERROR
        else:
            reasons.append(f'provider export missing: {pc.path}')
        statuses.append(ProviderStatus(pc.provider_id, pc.role, pc.priority, health, qh, surface, tuple(dict.fromkeys(reasons)), pc.serve_authorized, pc.predictive_status))
    evidence = _parse_evidence(workdir / 'acquisition/evidence/hard.json')
    evidence_errors = validate_evidence(evidence, official, now=now)
    b = SnapshotBuilder()
    b.add_json('official.json', dataclass_to_dict(official))
    b.add_json('official_raw.json', raw_official)
    b.add_json('team_state.json', dataclass_to_dict(team) if team else None)
    b.add_json('evidence.json', [dataclass_to_dict(r) for r in evidence])
    b.add_json('evidence_validation.json', {'errors': list(evidence_errors)})
    qmatrix = []
    for s in statuses:
        qmatrix.append({'provider_id': s.provider_id, 'role': s.role.value, 'priority': s.priority, 'health': s.health.value, 'qualification_by_horizon': {str(k): v.value for k, v in s.qualification_by_horizon.items()}, 'reasons': list(s.reasons), 'serve_authorized': s.serve_authorized, 'predictive_status': s.predictive_status.value})
        if s.surface:
            b.add_json(f'providers/{s.provider_id}.json', dataclass_to_dict(s.surface))
        pc = next((p for p in config.providers if p.provider_id == s.provider_id))
        path = workdir / pc.path
        if path.exists():
            b.add_bytes(f"provider_raw/{s.provider_id}{path.suffix or '.bin'}", path.read_bytes())
    b.add_json('qualification_matrix.json', qmatrix)
    b.add_json('run.json', {'schema_version': 1, 'run_id': run_id, 'code_sha': code_sha, 'config_sha': config_sha(config_path), 'run_started_at': run_started_at, 'acquired_at': now.isoformat(), 'target_gameweek': target, 'season': config.season, 'entry_id': config.entry_id, 'max_horizon': config.max_horizon, 'deadline': official.deadlines[target]})
    b.add_bytes('config.yaml', Path(config_path).read_bytes())
    return b.freeze(workdir / Path(config.snapshot_dir), metadata={'run_id': run_id, 'target_gameweek': target, 'code_sha': code_sha})
