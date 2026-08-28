from __future__ import annotations

from pathlib import Path
from typing import Any

CURRENT_SCORING_RULES_VERSION = "fpl-2026-27-v1"
REFERENCE_SCORING_RULES_VERSION = "openfpl-2024-25-rules"
REFERENCE_POSITIONS = ("GK", "DEF", "MID", "FWD", "AM")
REFERENCE_CV_FOLDS = tuple(range(1, 6))
REFERENCE_RUNTIME_DEPENDENCIES = (
    "pandas==2.3.1",
    "joblib==1.5.1",
    "xgboost==3.0.2",
    "scikit-learn==1.7.0",
)


def reference_asset_errors(root: str | Path) -> tuple[str, ...]:
    """Validate the immutable upstream reference layout without claiming currency."""
    root = Path(root)
    required = (
        "README.md",
        "play.ipynb",
        "plug.txt",
        "data/samples.csv",
        "models/features.save",
        "models/xscaler.save",
        "models/yscaler.save",
    )
    errors = [name for name in required if not (root / name).is_file()]
    for fold in REFERENCE_CV_FOLDS:
        for position in REFERENCE_POSITIONS:
            directory = root / "models" / f"cv{fold}_{position}"
            if not directory.is_dir():
                errors.append(f"missing model directory {directory.relative_to(root)}")
                continue
            if not (directory / "search.txt").is_file():
                errors.append(f"missing search log {(directory / 'search.txt').relative_to(root)}")
    return tuple(errors)


def current_model_manifest_errors(
    manifest: dict[str, Any],
    *,
    target_gameweek: int,
    source_snapshot: str,
) -> tuple[str, ...]:
    """Fail closed unless an OpenFPL adaptation is genuinely current and leakage-safe.

    The original 2024/25-labelled artifacts can be reproduced for reference, but they
    cannot be stamped with current Apex scoring provenance. A current challenger must
    declare a separately trained model artifact and a leakage audit.
    """
    errors: list[str] = []
    required = (
        "provider",
        "provider_version",
        "scoring_rules_version",
        "source_snapshot",
        "target_gameweek",
        "training_max_gameweek",
        "feature_contract_version",
        "model_artifact_sha256",
        "training_dataset_sha256",
        "placeholder_invariance",
        "official_forecast_coverage",
        "legacy_reference_weights_reused",
        "serve_authorized",
    )
    for key in required:
        if key not in manifest:
            errors.append(f"missing manifest field {key}")

    if str(manifest.get("provider", "")) != "openfpl":
        errors.append("provider must be openfpl")
    if str(manifest.get("scoring_rules_version", "")) != CURRENT_SCORING_RULES_VERSION:
        errors.append(
            "OpenFPL current model must be retrained/evaluated under "
            f"{CURRENT_SCORING_RULES_VERSION}"
        )
    if str(manifest.get("source_snapshot", "")) != str(source_snapshot):
        errors.append("OpenFPL source_snapshot does not match Official authority seal")
    try:
        manifest_target = int(manifest.get("target_gameweek"))
    except (TypeError, ValueError):
        manifest_target = -1
    if manifest_target != int(target_gameweek):
        errors.append("OpenFPL target_gameweek does not match production target")
    try:
        training_max = int(manifest.get("training_max_gameweek"))
    except (TypeError, ValueError):
        training_max = target_gameweek
    if training_max >= int(target_gameweek):
        errors.append("OpenFPL training data reaches target/future gameweek")
    if manifest.get("placeholder_invariance") is not True:
        errors.append("OpenFPL future-placeholder leakage audit did not pass")
    try:
        coverage = float(manifest.get("official_forecast_coverage"))
    except (TypeError, ValueError):
        coverage = -1.0
    if abs(coverage - 1.0) > 1e-12:
        errors.append("OpenFPL current model lacks 100% Official DecisionUniverse coverage")
    if manifest.get("legacy_reference_weights_reused") is not False:
        errors.append("legacy OpenFPL weights cannot be relabelled as a current-rules model")
    if manifest.get("serve_authorized") is not False:
        errors.append("OpenFPL must remain non-serving during prospective qualification")
    if not str(manifest.get("feature_contract_version", "")).strip():
        errors.append("OpenFPL feature contract version is empty")
    for key in ("model_artifact_sha256", "training_dataset_sha256"):
        value = str(manifest.get(key, ""))
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value.lower()):
            errors.append(f"{key} must be a SHA-256 hex digest")
    return tuple(dict.fromkeys(errors))
