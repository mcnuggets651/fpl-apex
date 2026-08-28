from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib, yaml
from apex.domain.models import ProviderRole, Qualification

@dataclass(frozen=True)
class ProviderConfig:
    provider_id: str
    role: ProviderRole
    priority: int
    serve_authorized: bool
    max_age_hours: float
    requested_horizons: tuple[int, ...]
    predictive_status: Qualification
    path: str

@dataclass(frozen=True)
class ApexConfig:
    season: str
    entry_id: int
    max_horizon: int
    providers: tuple[ProviderConfig, ...]
    snapshot_dir: str = 'data/v2/snapshots'
    release_prefix: str = 'apex-v2'

    @classmethod
    def load(cls, path):
        d = yaml.safe_load(Path(path).read_text())
        ps = []
        for p in d['providers']:
            ps.append(ProviderConfig(p['id'], ProviderRole(p['role']), int(p.get('priority', 100)), bool(p.get('serve_authorized', False)), float(p.get('max_age_hours', 18)), tuple(map(int, p.get('requested_horizons', [1]))), Qualification(p.get('predictive_status', 'INSUFFICIENT_HISTORY')), str(p['path'])))
        return cls(str(d.get('season', '2026-2027')), int(d['entry_id']), int(d.get('max_horizon', 8)), tuple(ps), str(d.get('snapshot_dir', 'data/v2/snapshots')), str(d.get('release_prefix', 'apex-v2')))

def config_sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
