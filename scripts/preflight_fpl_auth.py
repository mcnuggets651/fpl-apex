from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml
from cryptography.fernet import Fernet, InvalidToken

from apex.runtime.releases import GitHubReleaseStore, download_release_asset

BASE = "https://fantasy.premierleague.com/api"
DEFAULT_OIDC_CLIENT_ID = "bfcbaf69-aade-4c1b-8f00-c1cb8a193030"
DEFAULT_TOKEN_URL = "https://account.premierleague.com/as/token"
AUTH_TAG_PREFIX = "apex-v2/private-auth/"
AUTH_ASSET = "fpl_refresh_state.enc"


def _bearer_header(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    return value if value.casefold().startswith("bearer ") else f"Bearer {value}"


def _credential_candidates(
    *,
    token: str,
    cookie: str,
) -> list[tuple[str, dict[str, str]]]:
    common = {
        "Accept": "application/json",
        "Referer": "https://fantasy.premierleague.com/",
        "User-Agent": "fpl-apex-v2/1",
    }
    candidates: list[tuple[str, dict[str, str]]] = []
    bearer = _bearer_header(token)
    if bearer:
        candidates.append(("token", {**common, "X-API-Authorization": bearer}))
    if cookie.strip():
        candidates.append(("cookie", {**common, "Cookie": cookie.strip()}))
    return candidates


def _verify_headers(
    entry_id: int,
    *,
    headers: dict[str, str],
    http: Any = requests,
    timeout: float = 20.0,
) -> str:
    response = http.get(f"{BASE}/me/", headers=headers, timeout=timeout)
    if response.status_code in {401, 403}:
        return "rejected"
    if response.status_code != 200:
        raise RuntimeError("Official FPL owner-auth preflight returned an unexpected status")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Official FPL owner-auth preflight returned an invalid payload")
    authenticated_entry = (payload.get("player") or {}).get("entry")
    try:
        matches = int(authenticated_entry) == int(entry_id)
    except (TypeError, ValueError):
        matches = False
    return "match" if matches else "wrong_manager"


def verify_owner_credential(
    entry_id: int,
    *,
    token: str,
    cookie: str,
    http: Any = requests,
    timeout: float = 20.0,
) -> str:
    """Return the single proven direct auth transport without exposing secrets."""
    candidates = _credential_candidates(token=token, cookie=cookie)
    if not candidates:
        raise RuntimeError("Official FPL owner credential is not configured")

    rejected = 0
    wrong_manager = 0
    for mode, headers in candidates:
        status = _verify_headers(
            entry_id,
            headers=headers,
            http=http,
            timeout=timeout,
        )
        if status == "rejected":
            rejected += 1
            continue
        if status == "wrong_manager":
            wrong_manager += 1
            continue
        return mode

    if wrong_manager:
        raise RuntimeError("Official FPL credential belongs to a different manager entry")
    if rejected == len(candidates):
        raise RuntimeError("Official FPL owner credential was rejected or expired")
    raise RuntimeError("Official FPL owner credential could not be certified")


def _entry_id(config: Path) -> int:
    payload = yaml.safe_load(config.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("entry_id") is None:
        raise RuntimeError("Apex V2 config does not define entry_id")
    return int(payload["entry_id"])


def _private_store() -> GitHubReleaseStore | None:
    repo = os.getenv("APEX_PRIVATE_GITHUB_REPOSITORY", "").strip()
    token = os.getenv("APEX_PRIVATE_GITHUB_TOKEN", "").strip()
    if not repo and not token:
        return None
    if not repo or not token:
        raise RuntimeError("Private auth state requires the complete private-store configuration")
    return GitHubReleaseStore(repo, token)


def _fernet() -> Fernet | None:
    raw = os.getenv("FPL_REFRESH_WRAP_KEY", "").strip()
    if not raw:
        return None
    try:
        return Fernet(raw.encode("ascii"))
    except Exception as exc:
        raise RuntimeError("FPL refresh wrapping key is invalid") from exc


def _latest_private_refresh_token(store: GitHubReleaseStore, fernet: Fernet) -> str | None:
    releases = [
        row
        for row in store.list_releases()
        if str(row.get("tag_name") or "").startswith(AUTH_TAG_PREFIX)
        and not bool(row.get("draft", False))
    ]
    if not releases:
        return None
    release = max(
        releases,
        key=lambda row: str(row.get("created_at") or row.get("published_at") or ""),
    )
    with tempfile.TemporaryDirectory(prefix="apex-fpl-auth-") as tmp:
        path = download_release_asset(store, release, AUTH_ASSET, Path(tmp) / AUTH_ASSET)
        try:
            plaintext = fernet.decrypt(path.read_bytes())
        except InvalidToken as exc:
            raise RuntimeError("Encrypted FPL refresh state could not be decrypted") from exc
    payload = json.loads(plaintext.decode("utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise RuntimeError("Encrypted FPL refresh state has an invalid schema")
    token = str(payload.get("refresh_token") or "").strip()
    if not token:
        raise RuntimeError("Encrypted FPL refresh state omitted refresh_token")
    return token


def _persist_private_refresh_token(
    store: GitHubReleaseStore,
    fernet: Fernet,
    refresh_token: str,
) -> None:
    run_id = os.getenv("GITHUB_RUN_ID", "local").strip() or "local"
    attempt = os.getenv("GITHUB_RUN_ATTEMPT", "1").strip() or "1"
    tag = f"{AUTH_TAG_PREFIX}{run_id}-{attempt}"
    payload = {
        "schema_version": 1,
        "refresh_token": refresh_token,
        "stored_at": datetime.now(timezone.utc).isoformat(),
        "issuer": "https://account.premierleague.com/as",
        "client_id": os.getenv("FPL_OIDC_CLIENT_ID", DEFAULT_OIDC_CLIENT_ID),
    }
    encrypted = fernet.encrypt(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    with tempfile.TemporaryDirectory(prefix="apex-fpl-auth-") as tmp:
        path = Path(tmp) / AUTH_ASSET
        path.write_bytes(encrypted)
        store.create_once(
            tag,
            {AUTH_ASSET: path},
            target_commitish=None,
            name=f"Apex V2 encrypted FPL auth state {run_id}-{attempt}",
            body=(
                "Encrypted rotating FPL refresh-token state. Plaintext credentials "
                "must never be published or logged."
            ),
        )


def _exchange_refresh_token(
    refresh_token: str,
    *,
    http: Any = requests,
    timeout: float = 20.0,
) -> tuple[str, str]:
    token_url = os.getenv("FPL_TOKEN_URL", DEFAULT_TOKEN_URL).strip() or DEFAULT_TOKEN_URL
    client_id = (
        os.getenv("FPL_OIDC_CLIENT_ID", DEFAULT_OIDC_CLIENT_ID).strip()
        or DEFAULT_OIDC_CLIENT_ID
    )
    response = http.post(
        token_url,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        },
        timeout=timeout,
    )
    if response.status_code in {400, 401, 403}:
        raise RuntimeError("Official FPL refresh credential was rejected or expired")
    if response.status_code != 200:
        raise RuntimeError("Official FPL refresh exchange returned an unexpected status")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Official FPL refresh exchange returned an invalid payload")
    access_token = str(payload.get("access_token") or "").strip()
    next_refresh = str(payload.get("refresh_token") or refresh_token).strip()
    if not access_token or not next_refresh:
        raise RuntimeError("Official FPL refresh exchange omitted required token material")
    return access_token, next_refresh


def _refresh_owner_credential(
    entry_id: int,
    *,
    http: Any = requests,
    timeout: float = 20.0,
) -> tuple[str, str] | None:
    bootstrap = os.getenv("FPL_REFRESH_TOKEN", "").strip()
    fernet = _fernet()

    # Until refresh authentication is bootstrapped, preserve the independently
    # verified direct bearer/cookie path. The private manager repository existing
    # by itself does not imply that refresh state has been configured.
    if fernet is None and not bootstrap:
        return None

    store = _private_store()
    if store is None or fernet is None:
        raise RuntimeError(
            "FPL refresh authentication requires private storage and FPL_REFRESH_WRAP_KEY"
        )

    current = _latest_private_refresh_token(store, fernet) or bootstrap
    if not current:
        return None

    access_token, next_refresh = _exchange_refresh_token(
        current,
        http=http,
        timeout=timeout,
    )
    status = _verify_headers(
        entry_id,
        headers={
            "Accept": "application/json",
            "Referer": "https://fantasy.premierleague.com/",
            "User-Agent": "fpl-apex-v2/1",
            "X-API-Authorization": _bearer_header(access_token),
        },
        http=http,
        timeout=timeout,
    )
    if status == "wrong_manager":
        raise RuntimeError("Official FPL refresh credential belongs to a different manager entry")
    if status != "match":
        raise RuntimeError("Official FPL refreshed owner credential was rejected")

    # Persist the rotated refresh token before allowing the access token to escape
    # this boundary. If persistence fails, fail closed rather than consume rotation
    # state and strand the next production run.
    _persist_private_refresh_token(store, fernet, next_refresh)
    return access_token, next_refresh


def _write_runtime_env(path: Path, *, token: str = "", cookie: str = "") -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"FPL_X_API_AUTHORIZATION={token}\n")
        handle.write(f"FPL_SESSION_COOKIE={cookie}\n")


def _write_github_output(path: Path, mode: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"auth_mode={mode}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("config/apex_v2.yaml"))
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--github-env", type=Path)
    args = parser.parse_args()

    entry_id = _entry_id(args.config)
    refreshed = _refresh_owner_credential(entry_id)
    if refreshed is not None:
        access_token, _ = refreshed
        # Register generated access token as a GitHub log mask before any later step.
        print(f"::add-mask::{access_token}")
        if args.github_env:
            _write_runtime_env(args.github_env, token=access_token)
        mode = "refresh"
    else:
        token = os.getenv("FPL_X_API_AUTHORIZATION", "")
        cookie = os.getenv("FPL_SESSION_COOKIE", "")
        mode = verify_owner_credential(entry_id, token=token, cookie=cookie)
        if args.github_env:
            if mode == "token":
                _write_runtime_env(args.github_env, token=token)
            else:
                _write_runtime_env(args.github_env, cookie=cookie)

    if args.github_output:
        _write_github_output(args.github_output, mode)
    print(
        json.dumps(
            {
                "authenticated": True,
                "manager_identity_match": True,
                "auth_mode": mode,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
