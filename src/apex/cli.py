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


@app.command()
def intent(
    run_id: str,
    season: str,
    gameweek: int,
    code_sha: str,
    output: Path = Path("artifacts/v2/intent.json"),
    publish: bool = True,
):
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "season": season,
        "gameweek": gameweek,
        "code_sha": code_sha,
        "started_at": now,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    if publish:
        tag = f"apex-v2/intent/{season}/{run_id}"
        _store().create_once(
            tag,
            {"intent.json": output},
            target_commitish=code_sha,
            name=f"Apex V2 intent {season} GW{gameweek} {run_id}",
            body=(
                "Immutable production-attempt intent. A missing matching final "
                "release is an operational failure."
            ),
        )
    typer.echo(now)


@app.command()
def acquire(
    config: Path = Path("config/apex_v2.yaml"),
    run_id: str = typer.Option(...),
    code_sha: str = typer.Option(...),
    run_started_at: str = typer.Option(...),
    workdir: Path = Path("."),
):
    from apex.runtime.acquire import acquire_and_freeze

    snap = acquire_and_freeze(
        config,
        run_id=run_id,
        code_sha=code_sha,
        run_started_at=run_started_at,
        workdir=workdir,
    )
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
    season: str,
    gameweek: int,
    run_id: str,
    code_sha: str,
    artifact_dir: Path = Path("artifacts/v2"),
):
    from apex.runtime.releases import create_bundle_archive, write_attestation

    artifact_dir.mkdir(parents=True, exist_ok=True)
    bundle = artifact_dir / "bundle.tar.gz"
    attestation = artifact_dir / "attestation.json"
    payload = create_bundle_archive(snapshot, decision, bundle)
    payload.update(
        {
            "run_id": run_id,
            "season": season,
            "gameweek": gameweek,
            "code_sha": code_sha,
        }
    )
    write_attestation(attestation, payload)
    tag = f"apex-v2/final/{season}/{run_id}"
    ref = _store().create_once(
        tag,
        {
            "bundle.tar.gz": bundle,
            "attestation.json": attestation,
            "decision_bundle.json": decision,
        },
        target_commitish=code_sha,
        name=f"Apex V2 final {season} GW{gameweek} {run_id}",
        body=(
            "Immutable completed production attempt. Certification may be actionable "
            "or blocked; both are valid completed outcomes."
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
