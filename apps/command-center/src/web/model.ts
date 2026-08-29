import type {
  CommandCenterClassicV1,
  OfficialPlayerV1,
  ProjectionRowV1,
  SystemDecisionV1,
  TransferWeekV1,
} from "../shared/contract";

let liveVerificationCurrent = false;

export function setVerificationCurrent(value: boolean): void {
  liveVerificationCurrent = value;
}

export function verificationCurrent(): boolean {
  return liveVerificationCurrent;
}

export function playerMap(data: CommandCenterClassicV1): Map<number, OfficialPlayerV1> {
  return new Map(
    data.canonical_forecast.official.players.map((player) => [player.element_id, player]),
  );
}

export function projectionMap(
  data: CommandCenterClassicV1,
  horizon = 1,
): Map<number, ProjectionRowV1> {
  return new Map(
    data.canonical_forecast.rows
      .filter((row) => row.horizon === horizon)
      .map((row) => [row.element_id, row]),
  );
}

export function projectedXiScore(
  decision: SystemDecisionV1,
  rows: Map<number, ProjectionRowV1>,
): number | null {
  let total = 0;
  for (const playerId of decision.xi_ids) {
    const xp = rows.get(playerId)?.expected_points;
    if (xp === null || xp === undefined) return null;
    total += xp;
  }
  const captain = rows.get(decision.captain_id)?.expected_points;
  if (captain === null || captain === undefined) return null;
  return total + captain;
}

export function actionLabel(
  decision: SystemDecisionV1 | null,
  players: Map<number, OfficialPlayerV1>,
): string {
  if (!decision) return "NO ACTION";
  if (decision.transfers_in.length === 0 && decision.transfers_out.length === 0) {
    return "ROLL";
  }
  const pairs = decision.transfers_out.map((outId, index) => {
    const inId = decision.transfers_in[index];
    const outName = players.get(outId)?.web_name ?? `#${outId}`;
    const inName = players.get(inId)?.web_name ?? `#${inId}`;
    return `${outName} → ${inName}`;
  });
  return pairs.join(" · ");
}

export function actionReason(
  decision: SystemDecisionV1 | null,
  data: CommandCenterClassicV1,
): string {
  if (!decision) return data.capabilities.reason ?? "No personalized decision is available.";
  if (decision.transfers_in.length === 0) {
    return "The serving forecast and exact FPL mechanics do not justify spending a transfer this gameweek.";
  }
  const hit = decision.transfer_hits > 0 ? ` after ${decision.transfer_hits * 4} points of transfer hits` : "";
  return `This is Apex's maximum-EV legal current-gameweek action${hit}; future steps are shown only inside the qualified horizon.`;
}

export function teamName(data: CommandCenterClassicV1, teamId: number): string {
  return (
    data.canonical_forecast.official.teams.find((team) => team.id === teamId)?.short_name ??
    `T${teamId}`
  );
}

export function price(valueTenths: number | undefined | null): string {
  if (valueTenths === null || valueTenths === undefined) return "—";
  return `£${(valueTenths / 10).toFixed(1)}m`;
}

export function percent(value: number | undefined | null): string {
  if (value === null || value === undefined) return "—";
  return `${Math.round(value * 100)}%`;
}

export function fixtureLabel(
  data: CommandCenterClassicV1,
  fixtureIds: number[],
  playerTeamId: number,
): string {
  const byId = new Map(
    data.canonical_forecast.official.fixtures.map((fixture) => [fixture.fixture_id, fixture]),
  );
  return fixtureIds
    .map((fixtureId) => {
      const fixture = byId.get(fixtureId);
      if (!fixture) return `#${fixtureId}`;
      const home = fixture.home_team_id === playerTeamId;
      const opponentId = home ? fixture.away_team_id : fixture.home_team_id;
      return `${teamName(data, opponentId)} ${home ? "(H)" : "(A)"}`;
    })
    .join(", ");
}

export function visiblePlan(
  plan: TransferWeekV1[],
  maxQualifiedHorizon: number,
): TransferWeekV1[] {
  if (!liveVerificationCurrent) return [];
  return plan.filter(
    (week) => week.horizon >= 1 && week.horizon <= maxQualifiedHorizon,
  );
}

export function isActionCurrent(data: CommandCenterClassicV1, now = new Date()): boolean {
  if (!liveVerificationCurrent) return false;
  if (!data.capabilities.canonical_action_available) return false;
  const validUntil = data.public_attempt.certification.valid_until;
  if (!validUntil) return false;
  const expiry = new Date(validUntil);
  return Number.isFinite(expiry.getTime()) && now.getTime() < expiry.getTime();
}
