import type { ApiErrorV1, CommandCenterClassicV1 } from "../shared/contract";

const API_BASE = (import.meta.env.VITE_APEX_API_BASE as string | undefined)?.replace(/\/$/, "") ?? "";

export class ApexApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export async function fetchClassicLatest(signal?: AbortSignal): Promise<CommandCenterClassicV1> {
  const response = await fetch(`${API_BASE}/api/v1/classic/latest`, {
    method: "GET",
    headers: { Accept: "application/json" },
    credentials: "include",
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    let payload: ApiErrorV1 | null = null;
    try {
      payload = (await response.json()) as ApiErrorV1;
    } catch {
      // The UI never guesses from an unparseable response.
    }
    throw new ApexApiError(
      payload?.error ?? `http_${response.status}`,
      payload?.detail ?? "A current sealed Apex response is unavailable.",
    );
  }
  const payload = (await response.json()) as CommandCenterClassicV1;
  if (payload.schema_version !== 1 || payload.mode !== "CLASSIC") {
    throw new ApexApiError("contract_mismatch", "The Apex product contract is not supported by this client.");
  }
  return payload;
}
