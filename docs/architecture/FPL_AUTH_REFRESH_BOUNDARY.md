# FPL owner authentication refresh boundary

## Purpose

Apex V2 requires authenticated owner state from Official FPL for manager entry `63984` before it may certify personalized transfer decisions. The current FPL web application uses short-lived bearer access tokens, so a static `FPL_X_API_AUTHORIZATION` secret is not a durable production credential.

This boundary gives production a fail-closed, self-rotating refresh path without placing plaintext FPL credentials in Git history, public releases, diagnostics, provider archives, or workflow logs.

## Runtime contract

Production authenticates before opening a decision-attempt intent and before any expensive provider generation.

1. If refresh authentication is configured, load the most recent encrypted refresh state from the owner-private release store.
2. If no encrypted state exists yet, use the one-time `FPL_REFRESH_TOKEN` bootstrap secret.
3. Exchange the refresh token at the configured FPL/PingOne token endpoint for a short-lived access token and the next refresh token.
4. Verify the returned access token against Official FPL `/api/me/` and require exact manager entry `63984`.
5. Encrypt the rotated refresh token with the wrapping key held only in GitHub Actions secrets.
6. Persist the ciphertext as an immutable release in the owner-private repository.
7. Mask the generated access token and pass only that proven runtime token to the later authenticated acquisition step.
8. If refresh authentication has never been bootstrapped, the independently verified direct bearer/cookie path remains available as an emergency fallback.

No prediction/provider work begins until this boundary succeeds.

## Secrets and private state

### `FPL_REFRESH_TOKEN`

Bootstrap only. This must be a fresh refresh token for the correct FPL account. It is used only when no encrypted private auth-state release exists. After the first successful refresh-auth production run, the private encrypted state takes precedence over this bootstrap value, so the bootstrap secret may be removed.

Never commit it, print it, upload it, place it in an issue/PR, or paste it into ChatGPT.

### `FPL_REFRESH_WRAP_KEY`

Long-lived Fernet wrapping key. It remains only in GitHub Actions secrets and is required to decrypt/encrypt the rotating private refresh state. Losing this key makes existing encrypted auth releases unrecoverable; rotate the key only together with a new bootstrap refresh token.

Never commit or print it.

### `FPL_X_API_AUTHORIZATION`

Emergency/manual direct bearer fallback. Bearer access tokens are short-lived and must not be treated as durable production credentials.

### `FPL_SESSION_COOKIE`

Optional independently verified direct fallback. An empty cookie is valid configuration; Apex must not pretend it exists.

## Private immutable auth-state release

Repository: the configured owner-private Apex V2 repository (`APEX_V2_PRIVATE_REPOSITORY`).

Tag prefix:

`apex-v2/private-auth/`

Asset set:

- `fpl_refresh_state.enc`

The asset is Fernet ciphertext. Plaintext refresh/access tokens are forbidden from the release body, tag, filenames, diagnostics, public repository, and logs.

Apex chooses the newest non-draft private auth-state release, decrypts it only inside the production runner, and prefers it over the bootstrap secret.

## Identity and fail-closed rules

- A refreshed bearer is not accepted merely because token exchange returned HTTP 200.
- `/api/me/` must identify manager entry `63984` exactly.
- Wrong-manager credentials fail closed.
- Rejected/expired credentials fail closed.
- Malformed encrypted state fails closed.
- Missing or invalid wrapping key fails closed once refresh authentication has been bootstrapped.
- No credential value may appear in exception text.
- Diagnostic and evaluation workflows must never receive refresh/bootstrap/wrapping secrets.
- The authenticated owner-state money, squad and transfer contracts remain unchanged and are checked only after authentication succeeds.

## First bootstrap procedure

1. Log into the official Fantasy Premier League site in the browser as the owner of entry `63984`.
2. Obtain the current OIDC `refresh_token` from the authenticated browser session without posting or sending it anywhere else.
3. In GitHub repository settings for `mcnuggets651/fpl-apex`, create Actions secret `FPL_REFRESH_TOKEN` with that value.
4. Generate a Fernet key locally:

   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

5. Put that generated value directly into Actions secret `FPL_REFRESH_WRAP_KEY`.
6. Trigger exactly one authenticated Apex V2 production rehearsal.
7. Verify that the FPL auth preflight succeeds, a private immutable `apex-v2/private-auth/...` release is created with exactly one encrypted asset, `/api/me/` binds to entry `63984`, and no secret material appears in logs.
8. After a second successful production authentication using the encrypted private state, remove the bootstrap `FPL_REFRESH_TOKEN` secret if desired. Keep `FPL_REFRESH_WRAP_KEY`.

Do not trigger repeated production runs while bootstrap/rotation is failing.

## Recovery

If the refresh token is rejected, the wrapping key is lost, the encrypted state cannot be decrypted, or rotation state becomes unusable:

1. Do not weaken authentication or fall back to public manager state as editable truth.
2. Obtain a fresh owner refresh token from a newly authenticated Official FPL browser session.
3. If the wrapping key is still valid, replace only `FPL_REFRESH_TOKEN` after first resolving or deliberately superseding unusable private auth-state selection.
4. If the wrapping key is lost, generate a new wrapping key and bootstrap token together; never attempt to guess/decrypt historical ciphertext.
5. Run one fail-fast authenticated rehearsal and verify identity before provider work resumes.

## Security boundary

The public Apex repository can contain implementation, hashes, non-secret auth mode metadata and tests. It must never contain the manager's plaintext access token, refresh token, cookie, wrapping key, purchase/selling prices, bank, editable squad or transfer state.
