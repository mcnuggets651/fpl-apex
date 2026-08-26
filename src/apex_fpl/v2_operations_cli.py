"""Operator CLI for the V2 production backend and prospective empirical plane."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from apex_fpl.control.candidate_operations import (
    materialize_decision_policy_candidate,
    materialize_forecast_model_candidate,
    materialize_qualified_candidate,
)
from apex_fpl.control.production_backend_runtime import load_production_backend_runtime
from apex_fpl.control.prospective_experiment_operations import (
    declare_candidate_experiment,
    derive_candidate_qualification,
    qualification_supported,
    record_candidate_experiment_result,
)


app = typer.Typer(
    no_args_is_help=True,
    help=(
        "Fail-closed Apex V2 production operations. Requires APEX_PRODUCTION_POSTGRES_DSN; "
        "there is no filesystem fallback."
    ),
)


def _read_spec(path: Path) -> dict[str, object]:
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(f"spec is not readable UTF-8 JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise typer.BadParameter("spec must be a JSON object")
    return {str(key): value for key, value in raw.items()}


def _emit(payload: dict[str, object]) -> None:
    typer.echo(json.dumps(payload, sort_keys=True, indent=2))


def _store():
    return load_production_backend_runtime().artifact_store


@app.command("backend-identify")
def backend_identify() -> None:
    """Verify the configured production PostgreSQL backend and print credential-safe IDs."""

    runtime = load_production_backend_runtime()
    _emit(runtime.identity_payload())


@app.command("seal-file")
def seal_file(
    path: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False, readable=True),
    media_type: str = typer.Option("application/octet-stream"),
    schema_name: str | None = typer.Option(None),
    schema_version: str | None = typer.Option(None),
) -> None:
    """Seal one local evidence/parameter file into the immutable production ArtifactStore."""

    try:
        content = path.read_bytes()
    except OSError as exc:
        raise typer.BadParameter(f"cannot read file: {path}") from exc
    ref = _store().put_bytes(
        content,
        media_type=media_type,
        schema_name=schema_name,
        schema_version=schema_version,
    )
    _emit(
        {
            "schema_name": "apex-v2-seal-file-result",
            "schema_version": 1,
            "artifact_id": ref.artifact_id,
            "size": ref.size,
            "media_type": ref.media_type,
        }
    )


@app.command("materialize-model")
def materialize_model(
    spec: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False, readable=True),
) -> None:
    """Create a SHADOW forecast-model candidate; never changes the champion registry."""

    material = materialize_forecast_model_candidate(_read_spec(spec), store=_store())
    _emit(material.operator_payload())


@app.command("materialize-policy")
def materialize_policy(
    spec: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False, readable=True),
) -> None:
    """Create a SHADOW receding-horizon DecisionPolicy candidate."""

    material = materialize_decision_policy_candidate(_read_spec(spec), store=_store())
    _emit(material.operator_payload())


@app.command("experiment-declare")
def experiment_declare(
    candidate_artifact_id: str = typer.Argument(...),
    spec: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False, readable=True),
) -> None:
    """Predeclare an experiment using execution-time UTC; caller cannot backdate it."""

    material = declare_candidate_experiment(
        candidate_artifact_id,
        _read_spec(spec),
        store=_store(),
    )
    _emit(material.operator_payload())


@app.command("experiment-result")
def experiment_result(
    declaration_artifact_id: str = typer.Argument(...),
    spec: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False, readable=True),
) -> None:
    """Seal result evidence after the declared window; caller cannot set evaluated_at."""

    material = record_candidate_experiment_result(
        declaration_artifact_id,
        _read_spec(spec),
        store=_store(),
    )
    _emit(material.operator_payload())


@app.command("qualification-derive")
def qualification_derive(
    declaration_artifact_id: str = typer.Argument(...),
    result_artifact_id: str = typer.Argument(...),
) -> None:
    """Derive/replay qualification evidence without modifying any candidate champion."""

    material = derive_candidate_qualification(
        declaration_artifact_id,
        result_artifact_id,
        store=_store(),
    )
    _emit(material.operator_payload())
    if not qualification_supported(material):
        raise typer.Exit(code=2)


@app.command("candidate-qualify")
def candidate_qualify(
    candidate_artifact_id: str = typer.Argument(...),
    qualification_artifact_id: str = typer.Argument(...),
) -> None:
    """Materialize a QUALIFIED candidate row from exact SUPPORTED evidence; no auto-promotion."""

    material = materialize_qualified_candidate(
        candidate_artifact_id,
        qualification_artifact_id,
        store=_store(),
    )
    _emit(material.operator_payload())


if __name__ == "__main__":
    app()
