#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Mapping

REFRESH_REJECTION = "Official FPL refresh credential was rejected or expired"
MAX_PENDING_ROTATION_DEPTH = 8


class AuthOpsError(RuntimeError):
    """Operational authentication failure that must stop the workflow."""


class RefreshRejected(AuthOpsError):
    """A refresh-token grant was explicitly rejected/expired by Official FPL."""


class RefreshRotationIndeterminate(AuthOpsError):
    """A refresh exchange may have consumed its parent, but activation is unproven."""


def _load_frozen_auth(path: Path) -> ModuleType:
    """Load the authority-selected auth implementation supplied by the caller.

    The historical function name is retained for compatibility with existing
    operations tests. Production, keepalive and Draft relay pass the
    authority-selected production-core preflight rather than assuming the
    immutable forensic base is current authentication authority.
    """

    spec = importlib.util.spec_from_file_location("apex_v2_auth_preflight", path)
    if spec is None or spec.loader is None:
        raise AuthOpsError(f"Could not load owner-auth preflight: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _append_output(path: Path | None, key: str, value: str) -> None:
    if path is None:
        return
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{key}={value}\n")


def _preflight_command(
    preflight_script: Path,
    *,
    config: Path,
    github_output: Path | None,
    github_env: Path | None,
) -> list[str]:
    command = [sys.executable, str(preflight_script), "--config", str(config)]
    if github_output is not None:
        command.extend(["--github-output", str(github_output)])
    if github_env is not None:
        command.extend(["--github-env", str(github_env)])
    return command


def _run_frozen_preflight(
    preflight_script: Path,
    *,
    config: Path,
    github_output: Path | None,
    github_env: Path | None,
    env: Mapping[str, str],
) -> subprocess.CompletedProcess[str]:
    """Run the selected preflight only for the direct-credential proof path."""

    return subprocess.run(
        _preflight_command(
            preflight_script,
            config=config,
            github_output=github_output,
            github_env=github_env,
        ),
        env=dict(env),
        capture_output=True,
        text=True,
        check=False,
    )


def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return f"{result.stdout or ''}\n{result.stderr or ''}"


def _is_refresh_rejection(result: subprocess.CompletedProcess[str]) -> bool:
    return REFRESH_REJECTION in _combined_output(result)


def _show_success(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)


def _show_failure(result: subprocess.CompletedProcess[str]) -> None:
    # The selected preflight's failure text is required to remain credential-free.
    # GitHub also masks configured secrets. Keep the original bounded diagnostic
    # available for direct-auth incidents rather than replacing it with ambiguity.
    if result.stdout:
        print(result.stdout.rstrip(), file=sys.stderr)
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)


def _bootstrap_configured(env: Mapping[str, str]) -> bool:
    required = (
        "FPL_REFRESH_TOKEN",
        "FPL_REFRESH_WRAP_KEY",
        "APEX_PRIVATE_GITHUB_REPOSITORY",
        "APEX_PRIVATE_GITHUB_TOKEN",
    )
    return all(str(env.get(name, "")).strip() for name in required)


def _refresh_store_configured(env: Mapping[str, str]) -> bool:
    required = (
        "FPL_REFRESH_WRAP_KEY",
        "APEX_PRIVATE_GITHUB_REPOSITORY",
        "APEX_PRIVATE_GITHUB_TOKEN",
    )
    present = [bool(str(env.get(name, "")).strip()) for name in required]
    if any(present) and not all(present):
        raise AuthOpsError("Refresh authentication requires complete private-store configuration")
    return all(present)


def _direct_configured(env: Mapping[str, str]) -> bool:
    return bool(
        str(env.get("FPL_X_API_AUTHORIZATION", "")).strip()
        or str(env.get("FPL_SESSION_COOKIE", "")).strip()
    )


def _refresh_context(module: ModuleType, env: Mapping[str, str]):
    """Construct the encrypted private refresh store from explicit env mapping."""

    if not _refresh_store_configured(env):
        return None, None
    repo = str(env.get("APEX_PRIVATE_GITHUB_REPOSITORY", "")).strip()
    token = str(env.get("APEX_PRIVATE_GITHUB_TOKEN", "")).strip()
    wrap = str(env.get("FPL_REFRESH_WRAP_KEY", "")).strip()
    try:
        fernet = module.Fernet(wrap.encode("ascii"))
    except Exception as exc:
        raise AuthOpsError("FPL refresh wrapping key is invalid") from exc
    try:
        store = module.GitHubReleaseStore(repo, token)
    except Exception as exc:
        raise AuthOpsError("Could not initialize private FPL refresh store") from exc
    return store, fernet


def _require_two_phase_support(module: ModuleType, store) -> None:
    required_module = (
        "_exchange_refresh_token",
        "_verify_headers",
        "_bearer_header",
        "_refresh_transaction_fingerprint",
        "_rotation_tag",
        "_latest_private_refresh_token",
        "_write_runtime_env",
        "_write_github_output",
        "download_release_asset",
        "AUTH_ASSET",
        "DEFAULT_OIDC_CLIENT_ID",
    )
    if any(not hasattr(module, name) for name in required_module):
        raise AuthOpsError(
            "Authority-selected production core lacks two-phase refresh-rotation support"
        )
    required_store = (
        "list_releases",
        "_create_draft_and_upload",
        "_publish_draft",
        "_cleanup_mutable_release",
    )
    if any(not hasattr(store, name) for name in required_store):
        raise AuthOpsError(
            "Authority-selected private release store lacks staged refresh-rotation support"
        )


def _find_staged_draft(store, tag: str) -> dict | None:
    """Find an unpublished private rotation by tag through authenticated listing.

    GitHub's REST `releases/tags/{tag}` endpoint is explicitly for a *published*
    release. Draft releases are visible to push-authorized callers through List
    releases, so recovery must search that authenticated list instead of assuming
    the published-by-tag endpoint can see a draft.
    """

    matches = [
        item
        for item in store.list_releases()
        if bool(item.get("draft", False)) and str(item.get("tag_name") or "") == tag
    ]
    if len(matches) > 1:
        raise AuthOpsError("Private FPL refresh store contains duplicate staged rotation tags")
    return matches[0] if matches else None


def _read_staged_refresh(
    module: ModuleType,
    store,
    fernet,
    draft: dict,
    *,
    parent_refresh_token: str,
) -> str:
    expected = module._refresh_transaction_fingerprint(parent_refresh_token)
    with tempfile.TemporaryDirectory(prefix="apex-fpl-auth-recover-") as tmp:
        path = module.download_release_asset(
            store,
            draft,
            module.AUTH_ASSET,
            Path(tmp) / module.AUTH_ASSET,
        )
        try:
            plaintext = fernet.decrypt(Path(path).read_bytes())
        except Exception as exc:
            raise AuthOpsError("Staged FPL refresh rotation could not be decrypted") from exc
    try:
        payload = json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise AuthOpsError("Staged FPL refresh rotation has invalid JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise AuthOpsError("Staged FPL refresh rotation has an invalid schema")
    if payload.get("parent_fingerprint") != expected:
        raise AuthOpsError("Staged FPL refresh rotation does not match its parent")
    child = str(payload.get("refresh_token") or "").strip()
    if not child:
        raise AuthOpsError("Staged FPL refresh rotation omitted its child token")
    return child


def _stage_refresh_rotation(
    module: ModuleType,
    store,
    fernet,
    *,
    parent_refresh_token: str,
    next_refresh_token: str,
    env: Mapping[str, str],
) -> str:
    """Durably stage the rotated child as a PRIVATE draft before owner proof."""

    parent_fingerprint = module._refresh_transaction_fingerprint(parent_refresh_token)
    tag = module._rotation_tag(parent_fingerprint)
    if _find_staged_draft(store, tag) is not None:
        raise RefreshRotationIndeterminate(
            "A staged FPL refresh child already exists for the current parent; "
            "refuse duplicate rotation"
        )
    payload = {
        "schema_version": 1,
        "refresh_token": next_refresh_token,
        "parent_fingerprint": parent_fingerprint,
        "stored_at": datetime.now(timezone.utc).isoformat(),
        "issuer": "https://account.premierleague.com/as",
        "client_id": str(env.get("FPL_OIDC_CLIENT_ID", "")).strip()
        or module.DEFAULT_OIDC_CLIENT_ID,
    }
    encrypted = fernet.encrypt(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    with tempfile.TemporaryDirectory(prefix="apex-fpl-auth-stage-") as tmp:
        path = Path(tmp) / module.AUTH_ASSET
        path.write_bytes(encrypted)
        store._create_draft_and_upload(
            tag,
            {module.AUTH_ASSET: path},
            target_commitish=None,
            name=f"Apex V2 staged FPL auth rotation {parent_fingerprint}",
            body=(
                "Encrypted staged FPL refresh-token state. This draft is not active "
                "until exact owner identity verification succeeds."
            ),
        )
    return tag


def _recover_pending_chain(
    module: ModuleType,
    store,
    fernet,
    parent_refresh_token: str,
) -> tuple[str, tuple[str, ...]]:
    """Follow durable staged children without publishing or reusing dead parents."""

    current = parent_refresh_token
    tags: list[str] = []
    seen: set[str] = set()
    for _ in range(MAX_PENDING_ROTATION_DEPTH):
        fingerprint = module._refresh_transaction_fingerprint(current)
        if fingerprint in seen:
            raise AuthOpsError("FPL refresh staging chain contains a cycle")
        seen.add(fingerprint)
        tag = module._rotation_tag(fingerprint)
        draft = _find_staged_draft(store, tag)
        if draft is None:
            return current, tuple(tags)
        current = _read_staged_refresh(
            module,
            store,
            fernet,
            draft,
            parent_refresh_token=current,
        )
        tags.append(tag)
    fingerprint = module._refresh_transaction_fingerprint(current)
    if _find_staged_draft(store, module._rotation_tag(fingerprint)) is not None:
        raise AuthOpsError("FPL refresh staging chain exceeds bounded recovery depth")
    return current, tuple(tags)


def _activate_staged_rotation(module: ModuleType, store, tag: str) -> None:
    """Digest-verify and publish exactly the already-staged encrypted child."""

    draft = _find_staged_draft(store, tag)
    if draft is None:
        raise RefreshRotationIndeterminate("Verified staged FPL refresh child disappeared")
    with tempfile.TemporaryDirectory(prefix="apex-fpl-auth-activate-") as tmp:
        path = module.download_release_asset(
            store,
            draft,
            module.AUTH_ASSET,
            Path(tmp) / module.AUTH_ASSET,
        )
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        store._publish_draft(
            tag,
            int(draft["id"]),
            {module.AUTH_ASSET: digest},
            require_immutable=True,
        )


def _cleanup_superseded_drafts(store, tags: tuple[str, ...]) -> None:
    """Best-effort remove consumed intermediate staged drafts after activation."""

    for tag in tags:
        try:
            draft = _find_staged_draft(store, tag)
            if draft is not None:
                store._cleanup_mutable_release(int(draft["id"]), tag)
        except Exception:
            # The verified final child is already active. A stale private draft is
            # non-authoritative and may be cleaned later; never invalidate success.
            pass


def _verify_refreshed_access(module: ModuleType, entry_id: int, access_token: str) -> str:
    return module._verify_headers(
        entry_id,
        headers={
            "Accept": "application/json",
            "Referer": "https://fantasy.premierleague.com/",
            "User-Agent": "fpl-apex-v2/1",
            "X-API-Authorization": module._bearer_header(access_token),
        },
    )


def _rotate_refresh_parent(
    module: ModuleType,
    *,
    entry_id: int,
    store,
    fernet,
    parent_refresh_token: str,
    env: Mapping[str, str],
) -> tuple[str, str]:
    """Exchange -> stage private child -> verify owner -> activate child.

    Any failure after a successful exchange is indeterminate unless it is an
    explicit wrong-manager proof. The staged replacement is retained privately
    so a later run recovers from it instead of retrying a consumed parent.
    """

    current, recovered_tags = _recover_pending_chain(
        module, store, fernet, parent_refresh_token
    )
    try:
        access_token, next_refresh = module._exchange_refresh_token(current)
    except RuntimeError as exc:
        if str(exc) == REFRESH_REJECTION:
            raise RefreshRejected(REFRESH_REJECTION) from exc
        raise AuthOpsError(
            "Official FPL refresh exchange failed for an unclassified reason"
        ) from exc

    try:
        staged_tag = _stage_refresh_rotation(
            module,
            store,
            fernet,
            parent_refresh_token=current,
            next_refresh_token=next_refresh,
            env=env,
        )
    except RefreshRotationIndeterminate:
        raise
    except Exception as exc:
        raise RefreshRotationIndeterminate(
            "Official FPL refresh exchange succeeded but the rotated child could not "
            "be durably staged; do not retry the consumed parent"
        ) from exc

    try:
        status = _verify_refreshed_access(module, entry_id, access_token)
    except Exception as exc:
        raise RefreshRotationIndeterminate(
            "Official FPL refresh child is durably staged but owner verification is "
            "indeterminate; leave the draft inactive and retry through staged recovery"
        ) from exc

    if status == "wrong_manager":
        raise AuthOpsError(
            "Official FPL refreshed owner credential belongs to a different manager entry"
        )
    if status != "match":
        raise RefreshRotationIndeterminate(
            "Official FPL refresh child is durably staged but refreshed access could "
            "not be certified; leave the draft inactive and do not fall back"
        )

    try:
        _activate_staged_rotation(module, store, staged_tag)
    except RefreshRotationIndeterminate:
        raise
    except Exception as exc:
        raise RefreshRotationIndeterminate(
            "Official FPL owner identity matched but the staged refresh child could not "
            "be activated; retry only through staged recovery"
        ) from exc

    _cleanup_superseded_drafts(store, recovered_tags)
    return access_token, next_refresh


def _emit_refresh_success(
    module: ModuleType,
    *,
    access_token: str,
    github_output: Path | None,
    github_env: Path | None,
    recovery: str,
) -> None:
    print(f"::add-mask::{access_token}")
    if github_env is not None:
        module._write_runtime_env(github_env, token=access_token)
    if github_output is not None:
        module._write_github_output(github_output, "refresh")
    _append_output(github_output, "auth_recovery", recovery)
    print(
        json.dumps(
            {
                "authenticated": True,
                "manager_identity_match": True,
                "auth_mode": "refresh",
                "auth_recovery": recovery,
            },
            sort_keys=True,
        )
    )


def _bootstrap_recover(
    preflight_script: Path,
    *,
    config: Path,
    github_output: Path | None,
    github_env: Path | None,
    env: Mapping[str, str],
) -> None:
    """Force a fresh bootstrap through the same two-phase transaction boundary."""

    module = _load_frozen_auth(preflight_script)
    bootstrap = str(env.get("FPL_REFRESH_TOKEN", "")).strip()
    if not bootstrap:
        raise AuthOpsError("FPL bootstrap refresh token is not configured")
    store, fernet = _refresh_context(module, env)
    if store is None or fernet is None:
        raise AuthOpsError(
            "Bootstrap refresh recovery requires private storage and wrap key"
        )
    _require_two_phase_support(module, store)
    entry_id = module._entry_id(config)
    access_token, _ = _rotate_refresh_parent(
        module,
        entry_id=entry_id,
        store=store,
        fernet=fernet,
        parent_refresh_token=bootstrap,
        env=env,
    )
    _emit_refresh_success(
        module,
        access_token=access_token,
        github_output=github_output,
        github_env=github_env,
        recovery="bootstrap",
    )


def _direct_recover(
    preflight_script: Path,
    *,
    config: Path,
    github_output: Path | None,
    github_env: Path | None,
    env: Mapping[str, str],
) -> None:
    if not _direct_configured(env):
        raise AuthOpsError(
            "Refresh authentication failed and no direct owner credential is configured"
        )

    direct_env = dict(env)
    # Clearing both values makes the selected preflight skip refresh mode entirely
    # and exercise only its independently certified bearer/cookie owner proof.
    direct_env["FPL_REFRESH_TOKEN"] = ""
    direct_env["FPL_REFRESH_WRAP_KEY"] = ""
    result = _run_frozen_preflight(
        preflight_script,
        config=config,
        github_output=github_output,
        github_env=github_env,
        env=direct_env,
    )
    if result.returncode != 0:
        _show_failure(result)
        raise AuthOpsError("Direct owner-credential recovery could not be certified")
    _show_success(result)
    _append_output(github_output, "auth_recovery", "direct")


def _try_private_refresh(
    module: ModuleType,
    *,
    config: Path,
    github_output: Path | None,
    github_env: Path | None,
    env: Mapping[str, str],
) -> bool:
    store, fernet = _refresh_context(module, env)
    if store is None or fernet is None:
        return False
    _require_two_phase_support(module, store)
    try:
        parent = module._latest_private_refresh_token(store, fernet)
    except Exception as exc:
        raise AuthOpsError("Encrypted private FPL refresh state could not be loaded") from exc
    if not parent:
        return False
    entry_id = module._entry_id(config)
    access_token, _ = _rotate_refresh_parent(
        module,
        entry_id=entry_id,
        store=store,
        fernet=fernet,
        parent_refresh_token=parent,
        env=env,
    )
    _emit_refresh_success(
        module,
        access_token=access_token,
        github_output=github_output,
        github_env=github_env,
        recovery="none",
    )
    return True


def authenticate(
    *,
    mode: str,
    preflight_script: Path,
    config: Path,
    github_output: Path | None,
    github_env: Path | None,
    env: Mapping[str, str],
) -> str:
    """Run the serialized two-phase refresh transaction and bounded recovery ladder."""

    module = _load_frozen_auth(preflight_script)
    try:
        if _try_private_refresh(
            module,
            config=config,
            github_output=github_output,
            github_env=github_env,
            env=env,
        ):
            return "primary"
    except RefreshRejected:
        print(
            "Official FPL rejected the current rotating refresh state; "
            "entering bounded bootstrap recovery.",
            file=sys.stderr,
        )
    except RefreshRotationIndeterminate:
        # Never turn a staged-but-unverified rotation into a bootstrap/direct
        # fallback. The child is durable; recovery must resume from that draft.
        raise

    if _bootstrap_configured(env):
        try:
            _bootstrap_recover(
                preflight_script,
                config=config,
                github_output=github_output,
                github_env=github_env,
                env=env,
            )
            return "bootstrap"
        except RefreshRejected:
            print(
                "Configured bootstrap refresh token was also rejected/expired.",
                file=sys.stderr,
            )
        except RefreshRotationIndeterminate:
            raise

    if mode == "keepalive":
        raise AuthOpsError(
            "Refresh chain could not be renewed; keepalive cannot substitute direct auth"
        )

    _direct_recover(
        preflight_script,
        config=config,
        github_output=github_output,
        github_env=github_env,
        env=env,
    )
    return "direct"


def _format_wrapper_error(exc: Exception) -> str:
    if isinstance(exc, AuthOpsError):
        return f"Apex V2 auth operations failure: {type(exc).__name__}: {exc}"
    return (
        "Apex V2 auth operations failure: "
        f"{type(exc).__name__}: unexpected detail suppressed"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("production", "keepalive"), required=True)
    parser.add_argument(
        "--preflight-script",
        type=Path,
        default=Path("scripts/preflight_fpl_auth.py"),
    )
    parser.add_argument("--config", type=Path, default=Path("config/apex_v2.yaml"))
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--github-env", type=Path)
    args = parser.parse_args()

    try:
        authenticate(
            mode=args.mode,
            preflight_script=args.preflight_script,
            config=args.config,
            github_output=args.github_output,
            github_env=args.github_env,
            env=os.environ,
        )
    except Exception as exc:
        # AuthOpsError messages are deliberately static and secret-free. Arbitrary
        # exceptions are reduced to their type so a library/runtime error cannot
        # accidentally echo credential material into a GitHub Actions log.
        print(_format_wrapper_error(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
