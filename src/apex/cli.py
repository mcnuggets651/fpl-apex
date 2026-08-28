from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import typer

from apex.domain.models import dataclass_to_dict

app = typer.Typer(no_args_is_help=True)


def _store():
    from apex.runtime.releases import GitHubReleaseStore

    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")
    if not repo or not token:
        raise typer.BadParameter("GITHUB_REPOSITORY and GITHUB_TOKEN are required")
    return GitHubReleaseStore(repo, token)


def _private_store():
    from apex.runtime.releases import GitHubReleaseStore

    repo = os.environ.get("APEX_PRIVATE_GITHUB_REPOSITORY")
    token = os.environ.get("APEX_PRIVATE_GITHUB_TOKEN")
    if not repo or not token:
        raise typer.BadParameter(
            "authenticated manager publication requires "
            "APEX_PRIVATE_GITHUB_REPOSITORY and APEX_PRIVATE_GITHUB_TOKEN"
        )
    if repo == os.environ.get("GITHUB_REPOSITORY"):
        raise typer.BadParameter(
            "private manager store must be a separate repository"
        )
    return GitHubReleaseStore(repo, token)


@app.command()
def intent(
    run_id: str = typer.Option(..., "--run-id"),
    season: str = typer.Option(..., "--season"),
    gameweek: int = typer.Option(..., "--gameweek"),
    code_sha: str = typer.Option(..., "--code-sha"),
    output: Path = Path("artifacts/v2/intent.json"),
    publish: bool = True,
):
    from apex.runtime.publication import (
        INTENT_RELEASE_ASSETS_V1,
        assert_exact_asset_set,
        validate_intent_payload,
    )

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "season": season,
        "gameweek": gameweek,
        "code_sha": code_sha,
        "started_at": now,
    }
    validate_intent_payload(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    files = {"intent.json": output}
    assert_exact_asset_set(files, INTENT_RELEASE_ASSETS_V1, "intent release")
    if publish:
        tag = f"apex-v2/intent/{season}/{run_id}"
        _store().create_once(
            tag,
            files,
            target_commitish=code_sha,
            name=f"Apex V2 intent {season} GW{gameweek} {run_id}",
            body=(
                "Immutable production-attempt intent. A missing matching final "
                "release is an operational failure."
            ),
        )
    typer.echo(now)


@app.command("official-hash")
def official_hash(season: str = "2026-2027"):
    """Capture the canonical Official-FPL authority seal before acquisition."""
    from apex.sources.official import fetch_official_snapshot

    official, _ = fetch_official_snapshot(season=season)
    typer.echo(official.source_hash)


@app.command()
def acquire(
    config: Path = Path("config/apex_v2.yaml"),
    run_id: str = typer.Option(...),
    code_sha: str = typer.Option(...),
    run_started_at: str = typer.Option(...),
    workdir: Path = Path("."),
    expected_official_hash: str | None = typer.Option(
        None,
        "--expected-official-hash",
        help=(
            "Official FPL authority hash captured immediately before provider "
            "generation. Acquisition aborts if the final authority state differs."
        ),
    ),
    failure_output: Path = typer.Option(
        Path("artifacts/v2/acquisition_failure.json"),
        "--failure-output",
        help="Machine-readable fatal acquisition failure record.",
    ),
):
    from apex.runtime.acquire import AcquisitionStageError, acquire_and_freeze

    try:
        snap = acquire_and_freeze(
            config,
            run_id=run_id,
            code_sha=code_sha,
            run_started_at=run_started_at,
            workdir=workdir,
            expected_official_hash=expected_official_hash,
        )
    except AcquisitionStageError as exc:
        payload = {
            "schema_version": 1,
            "run_id": run_id,
            "code_sha": code_sha,
            "failed_at": datetime.now(timezone.utc).isoformat(),
            **exc.as_dict(),
        }
        failure_output.parent.mkdir(parents=True, exist_ok=True)
        failure_output.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        typer.echo(json.dumps(payload, sort_keys=True), err=True)
        raise typer.Exit(1) from exc
    typer.echo(str(snap.root))


@app.command()
def solve(
    snapshot: Path,
    output: Path = Path("artifacts/v2/decision_bundle.json"),
):
    from apex.runtime.solve import solve_snapshot

    bundle = solve_snapshot(snapshot, output)
    typer.echo(
        json.dumps(
            {
                "state": bundle.certification.state.value,
                "actionable": bundle.certification.actionable,
                "output": str(output),
            }
        )
    )


@app.command()
def publish(
    snapshot: Path,
    decision: Path,
    season: str = typer.Option(..., "--season"),
    gameweek: int = typer.Option(..., "--gameweek"),
    run_id: str = typer.Option(..., "--run-id"),
    code_sha: str = typer.Option(..., "--code-sha"),
    artifact_dir: Path = Path("artifacts/v2"),
):
    from apex.runtime.publication import build_publication_materials

    material = build_publication_materials(snapshot, decision, artifact_dir)

    # Persist owner-private state first. If it cannot be stored immutably, the
    # public final release is never created. This is the authenticated-run
    # kill switch and prevents a future fallback to the public repository.
    if material.authenticated_manager_state:
        private_ref = _private_store().create_once(
            f"apex-v2/private/{season}/{run_id}",
            material.private_files,
            target_commitish=code_sha,
            name=(
                f"Apex V2 private manager attempt {season} "
                f"GW{gameweek} {run_id}"
            ),
            body=(
                "Owner-private immutable manager attempt. Never mirror these "
                "assets into the public Apex repository."
            ),
        )
        if not private_ref.immutable:
            raise RuntimeError("private manager release is not immutable")

    tag = f"apex-v2/final/{season}/{run_id}"
    ref = _store().create_once(
        tag,
        material.public_files,
        target_commitish=code_sha,
        name=f"Apex V2 final {season} GW{gameweek} {run_id}",
        body=(
            "Immutable public production/audit attempt. Personalized manager "
            "state and decisions are structurally excluded from this release."
        ),
    )
    typer.echo(ref.html_url)


@app.command("audit-attempts")
def audit_attempts(prefix: str = "apex-v2"):
    from apex.runtime.attempts import audit_release_tags

    audit = audit_release_tags(_store().list_releases(), prefix)
    typer.echo(json.dumps(dataclass_to_dict(audit), indent=2))
    if audit.missing_finals:
        raise typer.Exit(2)


@app.command("evaluate-completed")
def evaluate_completed(
    season: str = "2026-2027",
    code_sha: str = typer.Option(...),
):
    from apex.runtime.evaluate import evaluate_completed_attempts

    tags = evaluate_completed_attempts(
        _store(),
        season=season,
        target_commitish=code_sha,
    )
    typer.echo(json.dumps({"published": tags}, indent=2))


if __name__ == "__main__":
    app()
