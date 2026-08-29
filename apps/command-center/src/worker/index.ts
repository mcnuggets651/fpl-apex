import type {
  ApiErrorV1,
  CommandCenterClassicV1,
  ManagerViewV1,
} from "../shared/contract";
import { verifyAccess } from "./access";
import {
  loadLatestPublic,
  loadPrivateForPublic,
  loadReview,
} from "./github";

export interface Env {
  PUBLIC_REPOSITORY: string;
  PUBLIC_GITHUB_TOKEN?: string;
  PRIVATE_REPOSITORY?: string;
  PRIVATE_GITHUB_TOKEN?: string;
  SEASON: string;
  ACCESS_TEAM_DOMAIN?: string;
  ACCESS_AUD?: string;
  ALLOWED_ORIGIN?: string;
}

function jsonResponse(
  payload: unknown,
  status = 200,
  headers: HeadersInit = {},
): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
      ...headers,
    },
  });
}

function errorResponse(error: string, status = 500, detail?: string): Response {
  const payload: ApiErrorV1 = {
    schema_version: 1,
    error,
    ...(detail ? { detail } : {}),
  };
  return jsonResponse(payload, status, { "Cache-Control": "no-store" });
}

function corsHeaders(request: Request, env: Env): HeadersInit {
  const origin = request.headers.get("Origin");
  if (!env.ALLOWED_ORIGIN || !origin || origin !== env.ALLOWED_ORIGIN) return {};
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "GET,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type,Cf-Access-Jwt-Assertion",
    "Access-Control-Allow-Credentials": "true",
    Vary: "Origin",
  };
}

function isExpired(validUntil: string | null, now = new Date()): boolean {
  if (!validUntil) return true;
  const parsed = new Date(validUntil);
  return !Number.isFinite(parsed.getTime()) || now.getTime() >= parsed.getTime();
}

function privateProofValid(manager: ManagerViewV1 | null): boolean {
  return Boolean(
    manager?.proof.immutable_private_release &&
      manager.proof.public_identity_match &&
      manager.proof.commitment_verified,
  );
}

export function actionAvailability(
  certification: {
    actionable: boolean;
    valid_until: string | null;
    state: string;
  },
  manager: ManagerViewV1 | null,
  now = new Date(),
): { available: boolean; reason: string | null } {
  if (isExpired(certification.valid_until, now)) {
    return { available: false, reason: "The sealed recommendation has expired." };
  }
  if (!certification.actionable) {
    return {
      available: false,
      reason: `Apex certification is ${certification.state.toLowerCase()}.`,
    };
  }
  if (!manager) {
    return {
      available: false,
      reason: "Private manager state is not connected for this sealed run.",
    };
  }
  if (!privateProofValid(manager)) {
    return {
      available: false,
      reason: "Private manager-state proof did not pass verification.",
    };
  }
  if (!manager.system_decision) {
    return {
      available: false,
      reason: "No personalized SystemDecision exists for this sealed run.",
    };
  }
  return { available: true, reason: null };
}

async function classicLatest(request: Request, env: Env): Promise<Response> {
  const cors = corsHeaders(request, env);
  const publicData = await loadLatestPublic(
    env.PUBLIC_REPOSITORY,
    env.SEASON,
    env.PUBLIC_GITHUB_TOKEN,
  );

  const access = await verifyAccess(
    request,
    env.ACCESS_TEAM_DOMAIN,
    env.ACCESS_AUD,
  );
  let manager: ManagerViewV1 | null = null;
  let privateForecast = null;
  if (
    access &&
    env.PRIVATE_REPOSITORY &&
    env.PRIVATE_GITHUB_TOKEN
  ) {
    const privateData = await loadPrivateForPublic(
      env.PRIVATE_REPOSITORY,
      env.PRIVATE_GITHUB_TOKEN,
      env.SEASON,
      publicData.attempt,
      publicData.forecast_commitment,
    );
    manager = privateData?.manager ?? null;
    privateForecast = privateData?.forecast ?? null;
  }

  const canonicalForecast = privateForecast ?? publicData.forecast;
  if (!canonicalForecast) {
    return errorResponse(
      "private_canonical_forecast_required",
      403,
      "The canonical display surface is private for this sealed run and requires verified owner access.",
    );
  }

  const review = await loadReview(
    env.PUBLIC_REPOSITORY,
    env.SEASON,
    publicData.attempt.run_id,
    env.PUBLIC_GITHUB_TOKEN,
  );
  const action = actionAvailability(
    publicData.attempt.certification,
    manager,
  );

  const payload: CommandCenterClassicV1 = {
    schema_version: 1,
    mode: "CLASSIC",
    fetched_at: new Date().toISOString(),
    public_release: publicData.summary,
    public_attempt: publicData.attempt,
    canonical_forecast: canonicalForecast,
    governance: publicData.governance,
    evidence: publicData.evidence,
    manager,
    review,
    capabilities: {
      canonical_action_available: action.available,
      private_manager_connected: manager !== null,
      review_available: Boolean(review.outcome || review.metrics),
      reason: action.reason,
    },
  };

  return jsonResponse(payload, 200, {
    ...cors,
    "Cache-Control": "private, no-store",
  });
}

async function handler(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const cors = corsHeaders(request, env);
  if (request.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: {
        ...cors,
        "Access-Control-Max-Age": "600",
      },
    });
  }
  if (request.method !== "GET") return errorResponse("method_not_allowed", 405);

  if (url.pathname === "/api/v1/health") {
    return jsonResponse(
      {
        schema_version: 1,
        ok: true,
        season: env.SEASON,
        private_manager_configured: Boolean(
          env.PRIVATE_REPOSITORY && env.PRIVATE_GITHUB_TOKEN,
        ),
      },
      200,
      { ...cors, "Cache-Control": "no-store" },
    );
  }
  if (url.pathname === "/api/v1/classic/latest") {
    try {
      return await classicLatest(request, env);
    } catch (error) {
      console.error("classic latest failed", {
        name: error instanceof Error ? error.name : "UnknownError",
        message: error instanceof Error ? error.message : "unknown",
      });
      return errorResponse(
        "apex_data_unavailable",
        503,
        "A current sealed Apex response could not be verified. No stale recommendation was served.",
      );
    }
  }
  return errorResponse("not_found", 404);
}

export default { fetch: handler };
