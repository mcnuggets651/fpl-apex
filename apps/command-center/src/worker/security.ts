const encoder = new TextEncoder();

export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  const object = value as Record<string, unknown>;
  return `{${Object.keys(object)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${canonicalJson(object[key])}`)
    .join(",")}}`;
}

export async function sha256Hex(data: ArrayBuffer | Uint8Array | string): Promise<string> {
  const bytes =
    typeof data === "string"
      ? encoder.encode(data)
      : data instanceof Uint8Array
        ? data
        : new Uint8Array(data);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function decodeBase64(value: string): Uint8Array {
  const binary = atob(value);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

function hexToBytes(value: string): Uint8Array {
  if (!/^[0-9a-f]{64}$/i.test(value)) {
    throw new Error("invalid SHA-256 hex digest");
  }
  return Uint8Array.from(value.match(/../g) ?? [], (pair) => Number.parseInt(pair, 16));
}

export async function verifyPrivateCommitment(
  reveal: Record<string, unknown>,
  commitment: Record<string, unknown>,
  keyBase64: string,
): Promise<boolean> {
  if (commitment.algorithm !== "HMAC-SHA256") return false;
  if (commitment.domain !== "apex-v2-private-decision-v1") return false;
  const keyBytes = decodeBase64(keyBase64);
  if (keyBytes.byteLength !== 32) return false;
  const key = await crypto.subtle.importKey(
    "raw",
    keyBytes,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"],
  );
  const message = encoder.encode(
    `apex-v2-private-decision-v1\u0000${canonicalJson(reveal)}`,
  );
  const digest = String(commitment.digest ?? "");
  if (!/^[0-9a-f]{64}$/i.test(digest)) return false;
  return crypto.subtle.verify("HMAC", key, hexToBytes(digest), message);
}

export function revealEligible(commitment: Record<string, unknown>, now = new Date()): boolean {
  const raw = commitment.reveal_not_before;
  if (typeof raw !== "string") return false;
  const date = new Date(raw);
  return Number.isFinite(date.getTime()) && now.getTime() >= date.getTime();
}
