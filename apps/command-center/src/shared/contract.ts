export type CertificationState =
  | "CERTIFIED"
  | "DEGRADED"
  | "BLOCKED"
  | "EXPIRED"
  | "INSUFFICIENT_HISTORY";

export type Position = "GK" | "DEF" | "MID" | "FWD";

export interface OfficialPlayerV1 {
  element_id: number;
  web_name: string;
  team_id: number;
  position: Position;
  price_tenths: number;
  status: string;
  can_transact: boolean;
  fpl_code: number | null;
}

export interface OfficialTeamV1 {
  id: number;
  name: string;
  short_name: string;
}

export interface OfficialFixtureV1 {
  fixture_id: number;
  gameweek: number | null;
  home_team_id: number;
  away_team_id: number;
  kickoff_time: string | null;
}

export interface OfficialCatalogV1 {
  schema_version: 1;
  season: string;
  acquired_at: string;
  source_hash: string;
  players: OfficialPlayerV1[];
  fixtures: OfficialFixtureV1[];
  deadlines: Record<string, string>;
  teams: OfficialTeamV1[];
}

export interface ProjectionRowV1 {
  element_id: number;
  gameweek: number;
  horizon: number;
  expected_points: number | null;
  fixture_ids: number[];
  n_fixtures: number;
  player_status_at_forecast: string | null;
  expected_minutes: number | null;
  p_appearance: number | null;
  p_start: number | null;
  p_60: number | null;
  coverage_status: "FORECAST" | "NO_FORECAST";
  coverage_reason: string | null;
  metadata: Record<string, never>;
  serving_provider_id: string;
}

export interface CanonicalForecastV1 {
  schema_version: 1;
  exposure_class: "PUBLIC_CANONICAL";
  season: string;
  target_gameweek: number;
  max_contiguous_qualified_horizon: number;
  serving_provider_by_horizon: Record<string, string>;
  provider_versions: Record<string, string>;
  scoring_rules_version: string | null;
  canonical_projection_sha256: string;
  official: OfficialCatalogV1;
  rows: ProjectionRowV1[];
}

export interface CertificationV1 {
  state: CertificationState;
  actionable: boolean;
  reasons: string[];
  // Optional only for backward compatibility with immutable Releases created
  // before the public serializer began exposing degradation warnings.
  warnings?: string[];
  valid_until: string | null;
}

export interface PrivateCommitmentV1 {
  schema_version: 1;
  algorithm: "HMAC-SHA256";
  domain: "apex-v2-private-decision-v1";
  digest: string;
  public_attempt_id: string;
  reveal_not_before: string;
}

export interface PublicAttemptV1 {
  schema_version: 1;
  season: string;
  target_gameweek: number;
  run_id: string;
  code_sha: string;
  config_sha: string;
  snapshot_id: string;
  official_snapshot_sha256: string;
  canonical_projection_sha256: string;
  serving_provider_by_horizon: Record<string, string>;
  max_contiguous_qualified_horizon: number;
  scoring_rules_version: string | null;
  frozen_at: string | null;
  public_attempt_id: string;
  exposure_class: "PUBLIC_CANONICAL";
  private_decision_commitment: PrivateCommitmentV1 | null;
  certification: CertificationV1;
}

export interface GovernanceV1 {
  schema_version: 1;
  exposure_class: "GOVERNANCE_PUBLIC";
  season: string;
  target_gameweek: number;
  qualification_matrix: Array<Record<string, unknown>>;
  certification: CertificationV1;
  max_contiguous_qualified_horizon: number;
  contingency_qualified_horizon: number;
  serving_provider_by_horizon: Record<string, string>;
  evidence_manifest: Record<string, unknown>;
  provider_archive_entries: Record<string, string>;
}

export interface EvidenceRowV1 {
  evidence_id: string;
  element_id: number;
  source_name: string;
  source_url: string;
  source_tier: string;
  published_at: string;
  retrieved_at: string;
  expires_at: string;
  evidence_type: string;
  gameweek: number;
  effect: "HARD_EXCLUDE" | "AUDIT_ONLY";
  content_hash: string;
  excerpt: string;
}

export interface EvidenceV1 {
  schema_version: 1;
  exposure_class: "PUBLIC_RESEARCH";
  rows: EvidenceRowV1[];
}

export interface TeamStateV1 {
  schema_version: 1;
  entry_id: number;
  published_gw: number;
  squad_ids: number[];
  bank_tenths: number;
  free_transfers: number;
  purchase_prices_tenths: Record<string, number>;
  selling_prices_tenths: Record<string, number>;
  active_chip: string | null;
  state_complete_for_transfers: boolean;
}

export interface SystemDecisionV1 {
  schema_version: 1;
  squad_ids: number[];
  xi_ids: number[];
  captain_id: number;
  vice_captain_id: number;
  bench_order: number[];
  transfers_in: number[];
  transfers_out: number[];
  objective: number;
  horizon: number;
  transfer_hits: number;
  decision_mode: string;
}

export interface TransferWeekV1 {
  horizon: number;
  gameweek: number;
  squad_ids: number[];
  transfers_in: number[];
  transfers_out: number[];
  bank_tenths: number;
  free_transfers: number;
  hits: number;
  submitted_ev: number;
}

export interface ManagerViewV1 {
  private_attempt_id: string;
  public_attempt_id: string;
  team_state: TeamStateV1;
  system_decision: SystemDecisionV1 | null;
  transfer_plan: TransferWeekV1[];
  proof: {
    immutable_private_release: boolean;
    public_identity_match: boolean;
    commitment_verified: boolean;
    reveal_eligible: boolean;
  };
}

export interface ReleaseSummaryV1 {
  tag: string;
  immutable: boolean;
  published_at: string | null;
  html_url: string | null;
}

export interface ReviewV1 {
  outcome: Record<string, unknown> | null;
  metrics: Record<string, unknown> | null;
}

export interface CommandCenterClassicV1 {
  schema_version: 1;
  mode: "CLASSIC";
  fetched_at: string;
  public_release: ReleaseSummaryV1;
  public_attempt: PublicAttemptV1;
  canonical_forecast: CanonicalForecastV1;
  governance: GovernanceV1;
  evidence: EvidenceV1;
  manager: ManagerViewV1 | null;
  review: ReviewV1;
  capabilities: {
    canonical_action_available: boolean;
    private_manager_connected: boolean;
    review_available: boolean;
    reason: string | null;
  };
}

export interface ApiErrorV1 {
  schema_version: 1;
  error: string;
  detail?: string;
}
