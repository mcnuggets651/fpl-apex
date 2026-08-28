from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def parse_utc(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

class Position(StrEnum):
    GK = 'GK'
    DEF = 'DEF'
    MID = 'MID'
    FWD = 'FWD'

@dataclass(frozen=True)
class OfficialPlayer:
    element_id: int
    web_name: str
    team_id: int
    position: Position
    price_tenths: int
    status: str
    can_transact: bool = True

@dataclass(frozen=True)
class OfficialFixture:
    fixture_id: int
    gameweek: int | None
    home_team_id: int
    away_team_id: int
    kickoff_time: str | None = None

@dataclass(frozen=True)
class OfficialSnapshot:
    schema_version: int
    season: str
    acquired_at: str
    source_hash: str
    players: tuple[OfficialPlayer, ...]
    fixtures: tuple[OfficialFixture, ...]
    deadlines: dict[int, str]

    @property
    def player_ids(self) -> frozenset[int]:
        return frozenset((p.element_id for p in self.players))

    def player_map(self) -> dict[int, OfficialPlayer]:
        return {p.element_id: p for p in self.players}

    def decision_universe(self, owned_player_ids: set[int] | frozenset[int]=frozenset()) -> frozenset[int]:
        ids = {p.element_id for p in self.players if p.can_transact}
        ids.update((int(pid) for pid in owned_player_ids if int(pid) in self.player_ids))
        return frozenset(ids)

class CoverageStatus(StrEnum):
    FORECAST = 'FORECAST'
    NO_FORECAST = 'NO_FORECAST'

@dataclass(frozen=True)
class ProjectionRow:
    element_id: int
    gameweek: int
    horizon: int
    expected_points: float | None
    fixture_ids: tuple[int, ...] = ()
    n_fixtures: int = 0
    player_status_at_forecast: str | None = None
    expected_minutes: float | None = None
    p_appearance: float | None = None
    p_start: float | None = None
    p_60: float | None = None
    coverage_status: CoverageStatus = CoverageStatus.FORECAST
    coverage_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)

@dataclass(frozen=True)
class ProjectionSurface:
    schema_version: int
    provider_id: str
    provider_version: str
    generated_at: str
    season: str
    source_snapshot: str
    scoring_rules_version: str
    supported_horizons: tuple[int, ...]
    runtime_dependencies: tuple[str, ...]
    rows: tuple[ProjectionRow, ...]

    def rows_for_horizon(self, horizon: int) -> tuple[ProjectionRow, ...]:
        return tuple((row for row in self.rows if row.horizon == int(horizon)))

@dataclass(frozen=True)
class ProductionProjectionSurface:
    """Serving-only projection view. Shadow/disagreement data cannot enter decisions."""
    schema_version: int
    provider_id: str
    provider_version: str
    generated_at: str
    season: str
    source_snapshot: str
    scoring_rules_version: str
    supported_horizons: tuple[int, ...]
    rows: tuple[ProjectionRow, ...]

    def rows_for_horizon(self, horizon: int) -> tuple[ProjectionRow, ...]:
        return tuple((row for row in self.rows if row.horizon == int(horizon)))

class ProviderRole(StrEnum):
    CHAMPION = 'CHAMPION'
    STANDBY = 'STANDBY'
    SHADOW = 'SHADOW'

class Qualification(StrEnum):
    QUALIFIED = 'QUALIFIED'
    UNQUALIFIED = 'UNQUALIFIED'
    DISQUALIFIED = 'DISQUALIFIED'
    INSUFFICIENT_HISTORY = 'INSUFFICIENT_HISTORY'

class ProviderHealth(StrEnum):
    HEALTHY = 'HEALTHY'
    STALE = 'STALE'
    INCOMPLETE = 'INCOMPLETE'
    ERROR = 'ERROR'

@dataclass(frozen=True)
class ProviderStatus:
    provider_id: str
    role: ProviderRole
    priority: int
    health: ProviderHealth
    qualification_by_horizon: dict[int, Qualification]
    surface: ProjectionSurface | None = None
    reasons: tuple[str, ...] = ()
    serve_authorized: bool = False
    predictive_status: Qualification = Qualification.INSUFFICIENT_HISTORY

    def qualified(self, horizon: int) -> bool:
        return self.qualification_by_horizon.get(int(horizon)) == Qualification.QUALIFIED

@dataclass(frozen=True)
class TeamState:
    schema_version: int
    entry_id: int
    published_gw: int
    squad_ids: tuple[int, ...]
    bank_tenths: int
    free_transfers: int
    purchase_prices_tenths: dict[int, int] = field(default_factory=dict)
    selling_prices_tenths: dict[int, int] = field(default_factory=dict)
    active_chip: str | None = None
    state_complete_for_transfers: bool = False

@dataclass(frozen=True)
class SystemDecision:
    schema_version: int
    squad_ids: tuple[int, ...]
    xi_ids: tuple[int, ...]
    captain_id: int
    vice_captain_id: int
    bench_order: tuple[int, ...]
    transfers_in: tuple[int, ...] = ()
    transfers_out: tuple[int, ...] = ()
    objective: float = 0.0
    horizon: int = 1
    transfer_hits: int = 0
    decision_mode: str = 'INITIAL_SQUAD'

@dataclass(frozen=True)
class ExecutionDecision:
    schema_version: int
    system_decision_hash: str
    actor: str
    recorded_at: str
    reason: str
    squad_ids: tuple[int, ...]
    xi_ids: tuple[int, ...]
    captain_id: int
    vice_captain_id: int
    bench_order: tuple[int, ...]
    transfers_in: tuple[int, ...] = ()
    transfers_out: tuple[int, ...] = ()

class EvidenceEffect(StrEnum):
    HARD_EXCLUDE = 'HARD_EXCLUDE'
    AUDIT_ONLY = 'AUDIT_ONLY'

@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    element_id: int
    source_name: str
    source_url: str
    source_tier: str
    published_at: str
    retrieved_at: str
    expires_at: str
    evidence_type: str
    gameweek: int
    effect: EvidenceEffect
    content_hash: str
    excerpt: str = ''

class CertificationState(StrEnum):
    CERTIFIED = 'CERTIFIED'
    DEGRADED = 'DEGRADED'
    BLOCKED = 'BLOCKED'
    EXPIRED = 'EXPIRED'
    INSUFFICIENT_HISTORY = 'INSUFFICIENT_HISTORY'

class ReasonCode(StrEnum):
    OFFICIAL_TRUTH_INVALID = 'OFFICIAL_TRUTH_INVALID'
    CHAMPION_UNAVAILABLE = 'CHAMPION_UNAVAILABLE'
    CHAMPION_STALE = 'CHAMPION_STALE'
    CHAMPION_INCOMPLETE = 'CHAMPION_INCOMPLETE'
    IDENTITY_INVALID = 'IDENTITY_INVALID'
    SNAPSHOT_INCOHERENT = 'SNAPSHOT_INCOHERENT'
    DECISION_ILLEGAL = 'DECISION_ILLEGAL'
    HARD_EVIDENCE_CONFLICT = 'HARD_EVIDENCE_CONFLICT'
    DEGRADED_ENRICHMENT = 'DEGRADED_ENRICHMENT'
    SHADOW_FAILURE = 'SHADOW_FAILURE'
    PUBLICATION_FAILED = 'PUBLICATION_FAILED'
    EXPECTED_ATTEMPT_MISSING = 'EXPECTED_ATTEMPT_MISSING'
    ATTEMPT_INCOMPLETE = 'ATTEMPT_INCOMPLETE'
    PERSISTENCE_INTEGRITY_VIOLATION = 'PERSISTENCE_INTEGRITY_VIOLATION'
    INSUFFICIENT_QUALIFIED_HORIZON = 'INSUFFICIENT_QUALIFIED_HORIZON'
    TEAM_STATE_INCOMPLETE = 'TEAM_STATE_INCOMPLETE'

@dataclass(frozen=True)
class CertificationResult:
    schema_version: int
    state: CertificationState
    actionable: bool
    reasons: tuple[ReasonCode, ...] = ()
    warnings: tuple[str, ...] = ()
    valid_until: str | None = None

@dataclass(frozen=True)
class RunManifest:
    schema_version: int
    run_id: str
    workflow_run_id: str | None
    season: str
    target_gameweek: int
    code_sha: str
    config_sha: str
    acquired_at: str
    snapshot_id: str
    serving_provider_by_horizon: dict[int, str]
    started_at: str = ''
    frozen_at: str = ''

@dataclass(frozen=True)
class DecisionBundle:
    schema_version: int
    manifest: RunManifest
    official_snapshot_hash: str
    canonical_projection_hash: str
    system_decision: SystemDecision | None
    certification: CertificationResult
    provider_diagnostics: dict[str, Any] = field(default_factory=dict)
    evidence_manifest: dict[str, Any] = field(default_factory=dict)

def dataclass_to_dict(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if hasattr(value, '__dataclass_fields__'):
        return {k: dataclass_to_dict(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): dataclass_to_dict(v) for k, v in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [dataclass_to_dict(v) for v in value]
    return value
