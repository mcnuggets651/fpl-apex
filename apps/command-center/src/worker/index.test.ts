import { describe, expect, it } from "vitest";

import type { ManagerViewV1 } from "../shared/contract";
import { actionAvailability } from "./index";

function manager(overrides: Partial<ManagerViewV1> = {}): ManagerViewV1 {
  return {
    private_attempt_id: "private",
    public_attempt_id: "public",
    team_state: {
      schema_version: 1,
      entry_id: 1,
      published_gw: 2,
      squad_ids: Array.from({ length: 15 }, (_, i) => i + 1),
      bank_tenths: 5,
      free_transfers: 2,
      purchase_prices_tenths: {},
      selling_prices_tenths: {},
      active_chip: null,
      state_complete_for_transfers: true,
    },
    system_decision: {
      schema_version: 1,
      squad_ids: Array.from({ length: 15 }, (_, i) => i + 1),
      xi_ids: Array.from({ length: 11 }, (_, i) => i + 1),
      captain_id: 1,
      vice_captain_id: 2,
      bench_order: [12, 13, 14, 15],
      transfers_in: [],
      transfers_out: [],
      objective: 60,
      horizon: 1,
      transfer_hits: 0,
      decision_mode: "TRANSFER_HORIZON",
    },
    transfer_plan: [],
    proof: {
      immutable_private_release: true,
      public_identity_match: true,
      commitment_verified: true,
      reveal_eligible: false,
    },
    ...overrides,
  };
}

const certified = {
  actionable: true,
  state: "CERTIFIED",
  valid_until: "2026-08-30T10:00:00Z",
};
const now = new Date("2026-08-29T08:00:00Z");

describe("BFF canonical action gate", () => {
  it("requires current certification and a verified private manager decision", () => {
    expect(actionAvailability(certified, manager(), now)).toEqual({
      available: true,
      reason: null,
    });
  });

  it("fails closed without private manager state", () => {
    expect(actionAvailability(certified, null, now).available).toBe(false);
  });

  it("fails closed when any private proof fails", () => {
    const broken = manager({
      proof: {
        immutable_private_release: true,
        public_identity_match: true,
        commitment_verified: false,
        reveal_eligible: false,
      },
    });
    expect(actionAvailability(certified, broken, now).available).toBe(false);
  });

  it("does not require post-deadline reveal eligibility for the authenticated owner", () => {
    const current = manager();
    expect(current.proof.reveal_eligible).toBe(false);
    expect(actionAvailability(certified, current, now).available).toBe(true);
  });

  it("fails closed after the sealed validity deadline", () => {
    expect(
      actionAvailability(certified, manager(), new Date("2026-08-30T10:00:00Z")).available,
    ).toBe(false);
  });

  it("fails closed when the sealed decision is blocked", () => {
    expect(
      actionAvailability(
        { ...certified, actionable: false, state: "BLOCKED" },
        manager(),
        now,
      ).available,
    ).toBe(false);
  });

  it("fails closed when the private release has no SystemDecision", () => {
    expect(
      actionAvailability(certified, manager({ system_decision: null }), now).available,
    ).toBe(false);
  });
});
