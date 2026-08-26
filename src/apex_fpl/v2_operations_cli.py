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

_MODEL_SPEC_FIELDS = frozenset(
    {
        "model_name",
        "model_version",
        "feature_contract",
        "prediction_contract",
        "parameter_artifact_ids",
        "valid_seasons",
        "qualification_season",
        "trained_through",
        "max_horizon_gameweeks",
    }
)
_POLICY_SPEC_FIELDS = frozenset(
    {
        "policy_name",
        "policy_version",
        "season",
        "evaluation_mode",
        "objective_policy",
        "horizon_gameweeks",
        "continuation_value_artifact_id",
        "chip_option_value_artifact_id",
        "price_policy_artifact_id",
        "candidate_policy_artifact_id",
        "tie_break_policy",
        "numeric_policy_id",
    }
)
_EXPERIMENT_SPEC_FIELDS = frozenset(
    {
        "proof_id",
        "evaluator_artifact_id",
        "policy_artifact_id",
        "evaluation_window_start",
        "evaluation_window_end",
        "minimum_sample_size",
        "metric_rules",
        "valid_until",
        "registry_artifact_id",
    }
)
_RESULT_SPEC_FIELDS = frozenset({"sample_size", "metrics", "source_artifact_ids"})


def _validate_spec(
    raw: dict[str, object],
    *,
    allowed_fields: frozenset[str],
    label: str,
) -> dict[str, object]:
    """Reject unknown/operator-owned fields instead of silently discarding them.

    Availability/declaration/result chronology is owned by the operator process. A typo or
    attempted backdating field must therefore fail closed rather than appear to have been
    accepted while being ignored.
    """

    unknown = sorted(set(raw) - allowed_fields)
    if unknown:
        raise typer.BadParameter(f"{label} contains unsupported fields: {unknown}")
    return raw


def _read_spec(
    path: Path,
    *,
    allowed_fields: frozenset[str],
    label: str,
) -> dict[str, object]:
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(f"spec is not readable UTF-8 JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise typer.BadParameter("spec must be a JSON object")
    normalized = {str(key): value for key, value in raw.items()}
    return _validate_spec(normalized, allowed_fields=allowed_fields, label=label)


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

    payload = _read_spec(spec, allowed_fields=_MODEL_SPEC_FIELDS, label="model spec")
    material = materialize_forecast_model_candidate(payload, store=_store())
    _emit(material.operator_payload())


@app.command("materialize-policy")
def materialize_policy(
    spec: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False, readable=True),
) -> None:
    """Create a SHADOW receding-horizon DecisionPolicy candidate."""

    payload = _read_spec(spec, allowed_fields=_POLICY_SPEC_FIELDS, label="policy spec")
    material = materialize_decision_policy_candidate(payload, store=_store())
    _emit(material.operator_payload())


@app.command("experiment-declare")
def experiment_declare(
    candidate_artifact_id: str = typer.Argument(...),
    spec: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False, readable=True),
) -> None:
    """Predeclare an experiment using execution-time UTC; caller cannot backdate it."""

    payload = _read_spec(spec, allowed_fields=_EXPERIMENT_SPEC_FIELDS, label="experiment spec")
    material = declare_candidate_experiment(
        candidate_artifact_id,
        payload,
        store=_store(),
    )
    _emit(material.operator_payload())


@app.command("experiment-result")
def experiment_result(
    declaration_artifact_id: str = typer.Argument(...),
    spec: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False, readable=True),
) -> None:
    """Seal result evidence after the declared window; caller cannot set evaluated_at."""

    payload = _read_spec(spec, allowed_fields=_RESULT_SPEC_FIELDS, label="result spec")
    material = record_candidate_experiment_result(
        declaration_artifact_id,
        payload,
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
