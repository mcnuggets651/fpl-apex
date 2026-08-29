import { afterEach, describe, expect, it } from "vitest";

import type {
  CommandCenterClassicV1,
  ProjectionRowV1,
  SystemDecisionV1,
  TransferWeekV1,
} from "../shared/contract";
import {
  certificationWarnings,
  isActionCurrent,
  playerMap,
  projectedXiScore,
  setVerificationCurrent,
  visiblePlan,
} from "./model";

function baseData(): CommandCenterClassicV1 {
  return {
    schema_version: 1,
    mode: "CLASSIC",
    fetched_at: "2026-08-29T07:00:00Z",
    public_release: {
      tag: "apex-v2/final/2026-2027/r1",
      immutable: true,
      published_at: "2026-08-29T07:00:00Z",
      html_url: null,
    },
    public_attempt: {
      schema_version: 1,
      season: "2026-2027",
      target_gameweek: 3,
      run_id: "r1",
      code_sha: "abc",
      config_sha: "cfg",
      snapshot_id: "snap",
      official_snapshot_sha256: "official",
      canonical_projection_sha256: "projection",
      serving_provider_by_horizon: { "1": "airsenal" },
      max_contiguous_qualified_horizon: 2,
      scoring_rules_version: "2026-2027",
      frozen_at: "2026-08-29T07:00:00Z",
      public_attempt_id: "attempt",
      exposure_class: "PUBLIC_CANONICAL",
      private_decision_commitment: null,
      certification: {
        state: "CERTIFIED",
        actionable: true,
        reasons: [],
        valid_until: "2026-08-30T10:00:00Z",
      },
    },
    canonical_forecast: {
      schema_version: 1,
      exposure_class: "PUBLIC_CANONICAL",
      season: "2026-2027",
      target_gameweek: 3,
      max_contiguous_qualified_horizon: 2,
      serving_provider_by_horizon: { "1": "airsenal", "2": "airsenal" },
      provider_versions: { airsenal: "v1" },
      scoring_rules_version: "2026-2027",
      canonical_projection_sha256: "projection",
      official: {
        schema_version: 1,
        season: "2026-2027",
        acquired_at: "2026-08-29T07:00:00Z",
        source_hash: "official",
        players: [
          { element_id: 1, web_name: "One", team_id: 1, position: "GK", price_tenths: 50, status: "a", can_transact: true, fpl_code: 101 },
          { element_id: 2, web_name: "Two", team_id: 2, position: "DEF", price_tenths: 55, status: "a", can_transact: true, fpl_code: 102 },
        ],
        fixtures: [],
        deadlines: { "3": "2026-08-30T10:00:00Z" },
        teams: [],
      },
      rows: [],
    },
    governance: {
      schema_version: 1,
      exposure_class: "GOVERNANCE_PUBLIC",
      season: "2026-2027",
      target_gameweek: 3,
      qualification_matrix: [],
      certification: {
        state: "CERTIFIED",
        actionable: true,
        reasons: [],
        valid_until: "2026-08-30T10:00:00Z",
      },
      max_contiguous_qualified_horizon: 2,
      serving_provider_by_horizon: { "1": "airsenal", "2": "airsenal" },
      evidence_manifest: {},
      provider_archive_entries: {},
    },
    evidence: { schema_version: 1, exposure_class: "PUBLIC_RESEARCH", rows: [] },
    manager: {
      private_attempt_id: "private",
      public_attempt_id: "attempt",
      team_state: {
        schema_version: 1,
        entry_id: 1,
        published_gw: 2,
        squad_ids: [1, 2],
        bank_tenths: 5,
        free_transfers: 2,
        purchase_prices_tenths: { "1": 50, "2": 55 },
        selling_prices_tenths: { "1": 50, "2": 55 },
        active_chip: null,
        state_complete_for_transfers: true,
      },
      system_decision: null,
      transfer_plan: [],
      proof: {
        immutable_private_release: true,
        public_identity_match: true,
        commitment_verified: true,
        reveal_eligible: false,
      },
    },
    review: { outcome: null, metrics: null },
    capabilities: {
      canonical_action_available: true,
      private_manager_connected: true,
      review_available: false,
      reason: null,
    },
  };
}

afterEach(() => setVerificationCurrent(false));

describe("browser action authority", () => {
  it("is false until the current BFF response has been verified", () => {
    const data = baseData();
    expect(isActionCurrent(data, new Date("2026-08-29T08:00:00Z"))).toBe(false);
    setVerificationCurrent(true);
    expect(isActionCurrent(data, new Date("2026-08-29T08:00:00Z"))).toBe(true);
  });

  it("is false for expired or server-blocked decisions", () => {
    const data = baseData();
    setVerificationCurrent(true);
    expect(isActionCurrent(data, new Date("2026-08-31T08:00:00Z"))).toBe(false);
    data.capabilities.canonical_action_available = false;
    expect(isActionCurrent(data, new Date("2026-08-29T08:00:00Z"))).toBe(false);
  });

  it("suppresses even a previously certified plan after verification is lost", () => {
    const plan: TransferWeekV1[] = [
      { horizon: 1, gameweek: 3, squad_ids: [], transfers_in: [], transfers_out: [], bank_tenths: 0, free_transfers: 2, hits: 0, submitted_ev: 5 },
      { horizon: 2, gameweek: 4, squad_ids: [], transfers_in: [], transfers_out: [], bank_tenths: 0, free_transfers: 1, hits: 0, submitted_ev: 6 },
      { horizon: 3, gameweek: 5, squad_ids: [], transfers_in: [], transfers_out: [], bank_tenths: 0, free_transfers: 1, hits: 0, submitted_ev: 7 },
    ];
    expect(visiblePlan(plan, 2)).toEqual([]);
    setVerificationCurrent(true);
    expect(visiblePlan(plan, 2).map((week) => week.horizon)).toEqual([1, 2]);
    setVerificationCurrent(false);
    expect(visiblePlan(plan, 2)).toEqual([]);
  });
});

describe("certification transparency", () => {
  it("surfaces degradation warnings and stays compatible with older releases", () => {
    const data = baseData();
    expect(certificationWarnings(data)).toEqual([]);

    data.public_attempt.certification.state = "DEGRADED";
    data.public_attempt.certification.warnings = [
      "appearance probabilities incomplete: contingent autosub/vice fallback EV is not included in primary objective",
    ];
    expect(certificationWarnings(data)).toEqual(data.public_attempt.certification.warnings);

    delete data.public_attempt.certification.warnings;
    expect(certificationWarnings(data)).toEqual([]);
  });
});

describe("deterministic ID-based joins and scoring", () => {
  it("maps players by Official element_id rather than display name", () => {
    const data = baseData();
    const players = playerMap(data);
    expect(players.get(2)?.web_name).toBe("Two");
    expect(players.has(999)).toBe(false);
  });

  it("adds the captain score exactly once on top of XI xP", () => {
    const decision: SystemDecisionV1 = {
      schema_version: 1,
      squad_ids: [1, 2],
      xi_ids: [1, 2],
      captain_id: 2,
      vice_captain_id: 1,
      bench_order: [],
      transfers_in: [],
      transfers_out: [],
      objective: 0,
      horizon: 1,
      transfer_hits: 0,
      decision_mode: "TRANSFER_HORIZON",
    };
    const rows = new Map<number, ProjectionRowV1>([
      [1, { element_id: 1, gameweek: 3, horizon: 1, expected_points: 4, fixture_ids: [], n_fixtures: 1, player_status_at_forecast: "a", expected_minutes: 90, p_appearance: 1, p_start: 1, p_60: 1, coverage_status: "FORECAST", coverage_reason: null, metadata: {}, serving_provider_id: "airsenal" }],
      [2, { element_id: 2, gameweek: 3, horizon: 1, expected_points: 6, fixture_ids: [], n_fixtures: 1, player_status_at_forecast: "a", expected_minutes: 90, p_appearance: 1, p_start: 1, p_60: 1, coverage_status: "FORECAST", coverage_reason: null, metadata: {}, serving_provider_id: "airsenal" }],
    ]);
    expect(projectedXiScore(decision, rows)).toBe(16);
  });
});
