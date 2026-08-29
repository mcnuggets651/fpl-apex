interface AccessClaims {
  aud?: string | string[];
  email?: string;
  exp?: number;
  iat?: number;
  nbf?: number;
  iss?: string;
  sub?: string;
}

interface JwkWithKid extends JsonWebKey {
  kid?: string;
}

let cachedKeys: { expiresAt: number; keys: JwkWithKid[] } | null = null;

function decodeBase64Url(value: string): Uint8Array {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(
    Math.ceil(value.length / 4) * 4,
    "=",
  );
  const binary = atob(padded);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

function decodeJson<T>(value: string): T {
  return JSON.parse(new TextDecoder().decode(decodeBase64Url(value))) as T;
}

async function accessKeys(teamDomain: string): Promise<JwkWithKid[]> {
  const now = Date.now();
  if (cachedKeys && cachedKeys.expiresAt > now) return cachedKeys.keys;
  const response = await fetch(`https://${teamDomain}/cdn-cgi/access/certs`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`Cloudflare Access certs HTTP ${response.status}`);
  const payload = (await response.json()) as { keys?: JwkWithKid[] };
  if (!Array.isArray(payload.keys) || payload.keys.length === 0) {
    throw new Error("Cloudflare Access returned no signing keys");
  }
  cachedKeys = { expiresAt: now + 10 * 60_000, keys: payload.keys };
  return payload.keys;
}

export async function verifyAccess(
  request: Request,
  teamDomain: string | undefined,
  audience: string | undefined,
): Promise<AccessClaims | null> {
  if (!teamDomain || !audience) return null;
  const token = request.headers.get("Cf-Access-Jwt-Assertion");
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  const header = decodeJson<{ alg?: string; kid?: string }>(parts[0]);
  if (header.alg !== "RS256" || !header.kid) return null;
  const claims = decodeJson<AccessClaims>(parts[1]);
  const now = Math.floor(Date.now() / 1000);
  if (!claims.exp || claims.exp <= now) return null;
  if (claims.nbf && claims.nbf > now + 30) return null;
  const expectedIssuer = `https://${teamDomain}`;
  if (claims.iss !== expectedIssuer) return null;
  const audiences = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
  if (!audiences.includes(audience)) return null;

  const key = (await accessKeys(teamDomain)).find((candidate) => candidate.kid === header.kid);
  if (!key) return null;
  const cryptoKey = await crypto.subtle.importKey(
    "jwk",
    key,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["verify"],
  );
  const signed = new TextEncoder().encode(`${parts[0]}.${parts[1]}`);
  const signature = decodeBase64Url(parts[2]);
  const valid = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5",
    cryptoKey,
    signature,
    signed,
  );
  return valid ? claims : null;
}
