import { describe, expect, it } from "vitest";

import { canonicalJson, verifyPrivateCommitment } from "./security";

const reveal = {
  schema_version: 1,
  public_attempt_id: "attempt-1",
  season: "2026-2027",
  target_gameweek: 3,
  decision_mode: "TRANSFER_HORIZON",
  transfers_in: [44],
  transfers_out: [12],
  xi_ids: [1, 2, 3],
  captain_id: 1,
  vice_captain_id: 2,
  bench_order: [4, 5],
  objective: 61.2,
  horizon: 2,
  transfer_hits: 0,
};

const commitment = {
  schema_version: 1,
  algorithm: "HMAC-SHA256",
  domain: "apex-v2-private-decision-v1",
  digest: "5d8915740965479f571f26fce54f4edab204dca628eba3d1feee9d048b738255",
};
const key = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=";

describe("private commitment interoperability", () => {
  it("matches the Python canonical JSON ordering used by Apex publication", () => {
    expect(canonicalJson(reveal)).toBe(
      '{"bench_order":[4,5],"captain_id":1,"decision_mode":"TRANSFER_HORIZON","horizon":2,"objective":61.2,"public_attempt_id":"attempt-1","schema_version":1,"season":"2026-2027","target_gameweek":3,"transfer_hits":0,"transfers_in":[44],"transfers_out":[12],"vice_captain_id":2,"xi_ids":[1,2,3]}',
    );
  });

  it("verifies an HMAC generated independently by Python", async () => {
    await expect(verifyPrivateCommitment(reveal, commitment, key)).resolves.toBe(true);
  });

  it("rejects a changed decision even with the original digest", async () => {
    await expect(
      verifyPrivateCommitment({ ...reveal, captain_id: 2 }, commitment, key),
    ).resolves.toBe(false);
  });
});
