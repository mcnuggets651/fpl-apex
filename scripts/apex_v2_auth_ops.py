#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Mapping

REFRESH_REJECTION = "Official FPL refresh credential was rejected or expired"


class AuthOpsError(RuntimeError):
    """Operational authentication failure that must stop the workflow."""


class RefreshRejected(AuthOpsError):
    """A refresh-token grant was explicitly rejected/expired by Official FPL."""


def _load_frozen_auth(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("apex_v2_frozen_preflight", path)
    if spec is None or spec.loader is None:
        raise AuthOpsError(f"Could not load frozen auth preflight: {path}")
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
    command = [
        sys.executable,
        str(preflight_script),
        "--config",
        str(config),
    ]
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
    # Frozen preflight failure text contains no credential material. GitHub also
    # masks configured secrets. Keep the original diagnostic available for
    # unexpected failures rather than replacing it with an ambiguous wrapper.
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


def _direct_configured(env: Mapping[str, str]) -> bool:
    return bool(
        str(env.get("FPL_X_API_AUTHORIZATION", "")).strip()
        or str(env.get("FPL_SESSION_COOKIE", "")).strip()
    )


def _bootstrap_recover(
    preflight_script: Path,
    *,
    config: Path,
    github_output: Path | None,
    github_env: Path | None,
    env: Mapping[str, str],
) -> None:
    """Force a fresh bootstrap token through the frozen rotate/persist boundary.

    The frozen preflight intentionally prefers encrypted private state over the
    bootstrap secret. That is correct during normal operation, but it means a
    dead private token would otherwise mask a newly re-seeded bootstrap secret.
    This recovery path is entered only after Official FPL explicitly rejects the
    current private refresh state.
    """

    module = _load_frozen_auth(preflight_script)
    bootstrap = str(env.get("FPL_REFRESH_TOKEN", "")).strip()
    if not bootstrap:
        raise AuthOpsError("FPL bootstrap refresh token is not configured")

    entry_id = module._entry_id(config)
    store = module._private_store()
    fernet = module._fernet()
    if store is None or fernet is None:
        raise AuthOpsError(
            "Bootstrap refresh recovery requires private storage and wrap key"
        )

    try:
        access_token, next_refresh = module._exchange_refresh_token(bootstrap)
    except RuntimeError as exc:
        if str(exc) == REFRESH_REJECTION:
            raise RefreshRejected(REFRESH_REJECTION) from exc
        raise

    # Reuse the frozen manager-identity proof. Wrong-manager and rejected-access
    # results remain hard failures.
    mode = module.verify_owner_credential(
        entry_id,
        token=access_token,
        cookie="",
    )
    if mode != "token":
        raise AuthOpsError("Bootstrap refresh did not certify bearer owner auth")

    # Persist the rotated refresh token before exposing the access token to later
    # steps. This preserves the certified no-stranding invariant.
    module._persist_private_refresh_token(store, fernet, next_refresh)

    print(f"::add-mask::{access_token}")
    if github_env is not None:
        module._write_runtime_env(github_env, token=access_token)
    if github_output is not None:
        module._write_github_output(github_output, "refresh")
    _append_output(github_output, "auth_recovery", "bootstrap")
    print(
        json.dumps(
            {
                "authenticated": True,
                "manager_identity_match": True,
                "auth_mode": "refresh",
                "auth_recovery": "bootstrap",
            },
            sort_keys=True,
        )
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
    # Clearing both values makes the frozen script skip refresh mode entirely and
    # exercise its independently certified direct bearer/cookie owner proof.
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


def authenticate(
    *,
    mode: str,
    preflight_script: Path,
    config: Path,
    github_output: Path | None,
    github_env: Path | None,
    env: Mapping[str, str],
) -> str:
    """Run certified auth, then only the explicitly allowed recovery ladder."""

    primary = _run_frozen_preflight(
        preflight_script,
        config=config,
        github_output=github_output,
        github_env=github_env,
        env=env,
    )
    if primary.returncode == 0:
        _show_success(primary)
        _append_output(github_output, "auth_recovery", "none")
        return "primary"

    if not _is_refresh_rejection(primary):
        _show_failure(primary)
        raise AuthOpsError(
            "Frozen FPL owner preflight failed for a non-recoverable reason"
        )

    print(
        "Official FPL rejected the current rotating refresh state; "
        "entering bounded auth recovery.",
        file=sys.stderr,
    )

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
        except Exception:
            # If a bootstrap exchange succeeds but identity proof/persistence fails,
            # the refresh state may have rotated. Never mask that with direct auth.
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
