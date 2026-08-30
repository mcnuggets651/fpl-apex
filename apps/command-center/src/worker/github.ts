import type {
  CanonicalForecastV1,
  EvidenceV1,
  GovernanceV1,
  ManagerViewV1,
  PublicAttemptV1,
  ReleaseSummaryV1,
  ReviewV1,
} from "../shared/contract";
import {
  canonicalJson,
  revealEligible,
  sha256Hex,
  verifyPrivateCommitment,
} from "./security";

const PUBLIC_ASSETS = new Set([
  "public_attempt.json",
  "canonical_forecast.json",
  "provider_forecasts.tar.gz",
  "governance.json",
  "evidence.json",
  "attestation.json",
]);
const PRIVATE_ASSETS = new Set([
  "private_manager_attempt.json",
  "private_attestation.json",
]);

interface GitHubAsset {
  name: string;
  url: string;
  digest?: string | null;
}

interface GitHubRelease {
  tag_name: string;
  draft: boolean;
  immutable?: boolean;
  published_at?: string | null;
  html_url?: string | null;
  assets: GitHubAsset[];
}

interface AttestationV2 {
  schema_version: number;
  scope: string;
  public_attempt_id: string;
  assets: Record<string, string>;
}

interface CanonicalForecastCommitmentV2 {
  schema_version: 2;
  exposure_class: "GOVERNANCE_PUBLIC";
  content_contract: "PROJECTION_COMMITMENT_ONLY_V2";
  forecast_rows_published: false;
  official_catalog_published: false;
  season: string;
  target_gameweek: number;
  max_contiguous_qualified_horizon: number;
  serving_provider_by_horizon: Record<string, string>;
  provider_versions: Record<string, string>;
  scoring_rules_version: string | null;
  canonical_projection_sha256: string;
  official_snapshot_sha256: string;
  private_canonical_forecast_sha256: string;
  projection_row_count: number;
  official_player_count: number;
  official_fixture_count: number;
}

interface PrivateManagerAttempt {
  schema_version: number;
  private_attempt_id: string;
  public_attempt_id: string;
  season: string;
  target_gameweek: number;
  team_state: Record<string, unknown>;
  system_decision: Record<string, unknown> | null;
  transfer_plan?: Array<Record<string, unknown>>;
  canonical_forecast_sha256?: string;
  canonical_forecast?: CanonicalForecastV1;
  reveal_record: Record<string, unknown>;
  commitment_key_b64: string;
}

function headers(token?: string): HeadersInit {
  return {
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2026-03-10",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

function assetMap(release: GitHubRelease): Map<string, GitHubAsset> {
  return new Map(release.assets.map((asset) => [asset.name, asset]));
}

function exactNames(release: GitHubRelease, expected: Set<string>): boolean {
  const actual = new Set(release.assets.map((asset) => asset.name));
  return actual.size === expected.size && [...expected].every((name) => actual.has(name));
}

function digestHex(asset: GitHubAsset): string | null {
  const digest = asset.digest ?? "";
  return digest.startsWith("sha256:") ? digest.slice(7) : null;
}

async function githubJson<T>(url: string, token?: string): Promise<T> {
  const response = await fetch(url, { headers: headers(token) });
  if (!response.ok) throw new Error(`GitHub HTTP ${response.status}: ${url}`);
  return (await response.json()) as T;
}

async function releaseByTag(
  repo: string,
  tag: string,
  token?: string,
): Promise<GitHubRelease | null> {
  const url = `https://api.github.com/repos/${repo}/releases/tags/${encodeURIComponent(tag)}`;
  const response = await fetch(url, { headers: headers(token) });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`GitHub HTTP ${response.status}: ${url}`);
  return (await response.json()) as GitHubRelease;
}

async function assetBytes(asset: GitHubAsset, token?: string): Promise<Uint8Array> {
  const response = await fetch(asset.url, {
    headers: {
      ...headers(token),
      Accept: "application/octet-stream",
    },
  });
  if (!response.ok) throw new Error(`GitHub asset HTTP ${response.status}: ${asset.name}`);
  return new Uint8Array(await response.arrayBuffer());
}

async function verifiedJson<T>(asset: GitHubAsset, token?: string): Promise<T> {
  const bytes = await assetBytes(asset, token);
  const githubDigest = digestHex(asset);
  if (!githubDigest) throw new Error(`GitHub omitted SHA-256 digest for ${asset.name}`);
  if ((await sha256Hex(bytes)) !== githubDigest) {
    throw new Error(`GitHub asset digest mismatch for ${asset.name}`);
  }
  return JSON.parse(new TextDecoder().decode(bytes)) as T;
}

function assertImmutable(release: GitHubRelease, label: string): void {
  if (release.draft || release.immutable !== true) {
    throw new Error(`${label} release is not published immutable`);
  }
}

function verifyAttestationAgainstGitHub(
  release: GitHubRelease,
  attestation: AttestationV2,
  expectedScope: string,
): void {
  if (attestation.schema_version !== 2 || attestation.scope !== expectedScope) {
    throw new Error(`${expectedScope} attestation contract mismatch`);
  }
  const assets = assetMap(release);
  for (const [name, expected] of Object.entries(attestation.assets)) {
    const asset = assets.get(name);
    if (!asset) throw new Error(`attestation references missing asset ${name}`);
    const githubDigest = digestHex(asset);
    if (!githubDigest || githubDigest !== expected) {
      throw new Error(`attestation/GitHub digest mismatch for ${name}`);
    }
  }
}

function isCommitmentV2(value: unknown): value is CanonicalForecastCommitmentV2 {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return (
    item.schema_version === 2 &&
    item.content_contract === "PROJECTION_COMMITMENT_ONLY_V2" &&
    item.forecast_rows_published === false &&
    item.official_catalog_published === false
  );
}

function isLegacyForecastV1(value: unknown): value is CanonicalForecastV1 {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return item.schema_version === 1 && Array.isArray(item.rows) && Boolean(item.official);
}

export interface LoadedPublic {
  release: GitHubRelease;
  summary: ReleaseSummaryV1;
  attempt: PublicAttemptV1;
  forecast: CanonicalForecastV1 | null;
  forecast_commitment: CanonicalForecastCommitmentV2 | null;
  governance: GovernanceV1;
  evidence: EvidenceV1;
}

export async function loadLatestPublic(
  repo: string,
  season: string,
  token?: string,
): Promise<LoadedPublic> {
  const releases = await githubJson<GitHubRelease[]>(
    `https://api.github.com/repos/${repo}/releases?per_page=100`,
    token,
  );
  const candidates = releases.filter(
    (release) =>
      !release.draft &&
      release.immutable === true &&
      release.tag_name.startsWith(`apex-v2/final/${season}/`) &&
      exactNames(release, PUBLIC_ASSETS),
  );
  if (candidates.length === 0) {
    throw new Error("no immutable Apex V2 public final using the V1 safe asset contract");
  }

  const inspected: Array<{ release: GitHubRelease; attempt: PublicAttemptV1 }> = [];
  for (const release of candidates.slice(0, 20)) {
    const asset = assetMap(release).get("public_attempt.json");
    if (!asset) continue;
    inspected.push({ release, attempt: await verifiedJson<PublicAttemptV1>(asset, token) });
  }
  inspected.sort((a, b) => {
    const gw = b.attempt.target_gameweek - a.attempt.target_gameweek;
    if (gw !== 0) return gw;
    return String(b.release.published_at ?? "").localeCompare(
      String(a.release.published_at ?? ""),
    );
  });
  const selected = inspected[0];
  if (!selected) throw new Error("no readable Apex V2 public final");
  const release = selected.release;
  const assets = assetMap(release);
  assertImmutable(release, "public");

  const [rawForecast, governance, evidence, attestation] = await Promise.all([
    verifiedJson<unknown>(assets.get("canonical_forecast.json")!, token),
    verifiedJson<GovernanceV1>(assets.get("governance.json")!, token),
    verifiedJson<EvidenceV1>(assets.get("evidence.json")!, token),
    verifiedJson<AttestationV2>(assets.get("attestation.json")!, token),
  ]);
  verifyAttestationAgainstGitHub(release, attestation, "PUBLIC");

  const attempt = selected.attempt;
  if (attestation.public_attempt_id !== attempt.public_attempt_id) {
    throw new Error("public attestation identity mismatch");
  }

  let forecast: CanonicalForecastV1 | null = null;
  let forecastCommitment: CanonicalForecastCommitmentV2 | null = null;
  if (isCommitmentV2(rawForecast)) {
    forecastCommitment = rawForecast;
    if (
      rawForecast.season !== season ||
      rawForecast.target_gameweek !== attempt.target_gameweek ||
      rawForecast.official_snapshot_sha256 !== attempt.official_snapshot_sha256 ||
      rawForecast.canonical_projection_sha256 !== attempt.canonical_projection_sha256 ||
      !/^[0-9a-f]{64}$/.test(rawForecast.private_canonical_forecast_sha256)
    ) {
      throw new Error("public canonical commitment identity mismatch");
    }
  } else if (isLegacyForecastV1(rawForecast)) {
    forecast = rawForecast;
    if (
      forecast.season !== season ||
      attempt.target_gameweek !== forecast.target_gameweek ||
      forecast.official.source_hash !== attempt.official_snapshot_sha256 ||
      forecast.canonical_projection_sha256 !== attempt.canonical_projection_sha256
    ) {
      throw new Error("legacy public canonical forecast identity mismatch");
    }
  } else {
    throw new Error("unsupported canonical forecast publication contract");
  }

  if (
    attempt.season !== season ||
    governance.season !== season ||
    attempt.target_gameweek !== governance.target_gameweek
  ) {
    throw new Error("public release season/gameweek identity mismatch");
  }

  return {
    release,
    summary: {
      tag: release.tag_name,
      immutable: true,
      published_at: release.published_at ?? null,
      html_url: release.html_url ?? null,
    },
    attempt,
    forecast,
    forecast_commitment: forecastCommitment,
    governance,
    evidence,
  };
}

function sameArray(a: unknown, b: unknown): boolean {
  return JSON.stringify(a ?? []) === JSON.stringify(b ?? []);
}

function revealMatchesDecision(
  reveal: Record<string, unknown>,
  decision: Record<string, unknown> | null,
): boolean {
  if (!decision) return reveal.decision_mode === "NO_DECISION";
  const scalarFields = [
    "decision_mode",
    "captain_id",
    "vice_captain_id",
    "objective",
    "horizon",
    "transfer_hits",
  ];
  if (scalarFields.some((field) => reveal[field] !== decision[field])) return false;
  return ["transfers_in", "transfers_out", "xi_ids", "bench_order"].every((field) =>
    sameArray(reveal[field], decision[field]),
  );
}

export interface LoadedPrivateForPublic {
  manager: ManagerViewV1;
  forecast: CanonicalForecastV1 | null;
}

export async function loadPrivateForPublic(
  privateRepo: string,
  token: string,
  season: string,
  publicAttempt: PublicAttemptV1,
  forecastCommitment: CanonicalForecastCommitmentV2 | null = null,
): Promise<LoadedPrivateForPublic | null> {
  const tag = `apex-v2/private/${season}/${publicAttempt.run_id}`;
  const release = await releaseByTag(privateRepo, tag, token);
  if (!release) return null;
  assertImmutable(release, "private manager");
  if (!exactNames(release, PRIVATE_ASSETS)) {
    throw new Error("private manager release asset contract mismatch");
  }
  const assets = assetMap(release);
  const [payload, attestation] = await Promise.all([
    verifiedJson<PrivateManagerAttempt>(assets.get("private_manager_attempt.json")!, token),
    verifiedJson<AttestationV2>(assets.get("private_attestation.json")!, token),
  ]);
  verifyAttestationAgainstGitHub(release, attestation, "PRIVATE_MANAGER");
  if (attestation.public_attempt_id !== publicAttempt.public_attempt_id) {
    throw new Error("private attestation/public attempt identity mismatch");
  }

  const commitment = publicAttempt.private_decision_commitment;
  if (!commitment) throw new Error("private release exists without public commitment");
  const identityMatch =
    payload.public_attempt_id === publicAttempt.public_attempt_id &&
    payload.season === publicAttempt.season &&
    payload.target_gameweek === publicAttempt.target_gameweek &&
    payload.reveal_record.public_attempt_id === publicAttempt.public_attempt_id &&
    payload.reveal_record.season === publicAttempt.season &&
    payload.reveal_record.target_gameweek === publicAttempt.target_gameweek &&
    commitment.public_attempt_id === publicAttempt.public_attempt_id;
  if (!identityMatch) throw new Error("private/public attempt identity mismatch");
  if (!revealMatchesDecision(payload.reveal_record, payload.system_decision)) {
    throw new Error("private reveal record does not match stored SystemDecision");
  }
  const commitmentVerified = await verifyPrivateCommitment(
    payload.reveal_record,
    commitment as unknown as Record<string, unknown>,
    payload.commitment_key_b64,
  );
  if (!commitmentVerified) throw new Error("private decision commitment failed verification");

  let privateForecast: CanonicalForecastV1 | null = null;
  if (forecastCommitment) {
    if (!payload.canonical_forecast || !payload.canonical_forecast_sha256) {
      throw new Error("private canonical forecast missing for public commitment");
    }
    const computed = await sha256Hex(canonicalJson(payload.canonical_forecast));
    if (
      computed !== payload.canonical_forecast_sha256 ||
      computed !== forecastCommitment.private_canonical_forecast_sha256
    ) {
      throw new Error("private canonical forecast hash verification failed");
    }
    if (
      payload.canonical_forecast.season !== publicAttempt.season ||
      payload.canonical_forecast.target_gameweek !== publicAttempt.target_gameweek ||
      payload.canonical_forecast.official.source_hash !== publicAttempt.official_snapshot_sha256 ||
      payload.canonical_forecast.canonical_projection_sha256 !==
        publicAttempt.canonical_projection_sha256 ||
      payload.canonical_forecast.rows.length !== forecastCommitment.projection_row_count ||
      payload.canonical_forecast.official.players.length !==
        forecastCommitment.official_player_count ||
      payload.canonical_forecast.official.fixtures.length !==
        forecastCommitment.official_fixture_count
    ) {
      throw new Error("private canonical forecast/public commitment identity mismatch");
    }
    privateForecast = payload.canonical_forecast;
  }

  const manager: ManagerViewV1 = {
    private_attempt_id: payload.private_attempt_id,
    public_attempt_id: payload.public_attempt_id,
    team_state: payload.team_state as unknown as ManagerViewV1["team_state"],
    system_decision: payload.system_decision as unknown as ManagerViewV1["system_decision"],
    transfer_plan: (payload.transfer_plan ?? []) as unknown as ManagerViewV1["transfer_plan"],
    proof: {
      immutable_private_release: true,
      public_identity_match: true,
      commitment_verified: true,
      reveal_eligible: revealEligible(commitment as unknown as Record<string, unknown>),
    },
  };

  return { manager, forecast: privateForecast };
}

async function optionalSingleAssetRelease(
  repo: string,
  tag: string,
  assetName: string,
  token?: string,
): Promise<Record<string, unknown> | null> {
  const release = await releaseByTag(repo, tag, token);
  if (!release) return null;
  assertImmutable(release, tag);
  if (!exactNames(release, new Set([assetName]))) {
    throw new Error(`${tag} asset contract mismatch`);
  }
  return verifiedJson<Record<string, unknown>>(assetMap(release).get(assetName)!, token);
}

export async function loadReview(
  repo: string,
  season: string,
  runId: string,
  token?: string,
): Promise<ReviewV1> {
  const [outcome, metrics] = await Promise.all([
    optionalSingleAssetRelease(repo, `apex-v2/outcome/${season}/${runId}`, "outcomes.json", token),
    optionalSingleAssetRelease(repo, `apex-v2/evaluation/${season}/${runId}`, "metrics.json", token),
  ]);
  return { outcome, metrics };
}
