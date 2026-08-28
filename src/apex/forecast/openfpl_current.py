from __future__ import annotations

from pathlib import Path
from typing import Any

CURRENT_SCORING_RULES_VERSION = "fpl-2026-27-v1"
CURRENT_EXACT_RULE_SEASON = "2026-27"
REFERENCE_SCORING_RULES_VERSION = "openfpl-2024-25-rules"
REFERENCE_POSITIONS = ("GK", "DEF", "MID", "FWD", "AM")
REFERENCE_CV_FOLDS = tuple(range(1, 6))
REFERENCE_ROLLING_WINDOWS = (1, 3, 5, 10, 38)
REFERENCE_RUNTIME_DEPENDENCIES = (
    "pandas==2.3.1",
    "joblib==1.5.1",
    "xgboost==3.0.2",
    "scikit-learn==1.7.0",
)
# These reference inputs encode the scoring regime in which they were observed.
# They are why old feature rows cannot simply be relabelled as 2026/27-current.
SCORE_DEPENDENT_REFERENCE_FEATURE_FAMILIES = (
    "fpl_points",
    "bps",
    "bonus",
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


def exact_rule_history_readiness(
    completed_gameweeks: tuple[int, ...] | list[int] | set[int],
    *,
    target_gameweek: int,
    minimum_exact_rule_gameweeks: int | None = None,
) -> dict[str, Any]:
    """Describe OpenFPL retraining readiness without inventing a sample threshold.

    A minimum is deliberately not hard-coded. Until a governed training policy chooses
    one, exact current-rule history can be observed and audited but cannot authorize a
    retrain. Once a minimum is approved, this function advances deterministically.
    """
    gameweeks = tuple(sorted({int(gameweek) for gameweek in completed_gameweeks}))
    future = tuple(gameweek for gameweek in gameweeks if gameweek >= int(target_gameweek))
    if future:
        return {
            "state": "HISTORY_LEAKAGE",
            "training_ready": False,
            "completed_exact_rule_gameweeks": list(gameweeks),
            "exact_rule_gameweek_count": len(gameweeks),
            "target_gameweek": int(target_gameweek),
            "minimum_exact_rule_gameweeks": minimum_exact_rule_gameweeks,
            "reasons": [
                "exact-rule history contains target/future gameweeks: "
                + ",".join(str(gameweek) for gameweek in future)
            ],
        }
    if not gameweeks:
        return {
            "state": "NO_EXACT_RULE_HISTORY",
            "training_ready": False,
            "completed_exact_rule_gameweeks": [],
            "exact_rule_gameweek_count": 0,
            "target_gameweek": int(target_gameweek),
            "minimum_exact_rule_gameweeks": minimum_exact_rule_gameweeks,
            "reasons": ["no completed 2026/27 exact-rule gameweeks are available"],
        }
    if minimum_exact_rule_gameweeks is None:
        return {
            "state": "TRAINING_POLICY_UNSET",
            "training_ready": False,
            "completed_exact_rule_gameweeks": list(gameweeks),
            "exact_rule_gameweek_count": len(gameweeks),
            "target_gameweek": int(target_gameweek),
            "minimum_exact_rule_gameweeks": None,
            "reasons": [
                "exact-rule history exists but no governed minimum training sample "
                "has been approved; Apex will not invent one"
            ],
        }
    minimum = int(minimum_exact_rule_gameweeks)
    if minimum < 1:
        raise ValueError("minimum_exact_rule_gameweeks must be >= 1")
    if len(gameweeks) < minimum:
        return {
            "state": "CURRENT_LABEL_HISTORY_INSUFFICIENT",
            "training_ready": False,
            "completed_exact_rule_gameweeks": list(gameweeks),
            "exact_rule_gameweek_count": len(gameweeks),
            "target_gameweek": int(target_gameweek),
            "minimum_exact_rule_gameweeks": minimum,
            "reasons": [
                f"{len(gameweeks)} exact-rule gameweeks available; governed minimum is {minimum}"
            ],
        }
    return {
        "state": "CURRENT_LABEL_HISTORY_READY",
        "training_ready": True,
        "completed_exact_rule_gameweeks": list(gameweeks),
        "exact_rule_gameweek_count": len(gameweeks),
        "target_gameweek": int(target_gameweek),
        "minimum_exact_rule_gameweeks": minimum,
        "reasons": [],
    }


def current_model_manifest_errors(
    manifest: dict[str, Any],
    *,
    target_gameweek: int,
    source_snapshot: str,
) -> tuple[str, ...]:
    """Fail closed unless an OpenFPL adaptation is genuinely current and leakage-safe.

    The original 2024/25-labelled artifacts can be reproduced for reference, but they
    cannot be stamped with current Apex scoring provenance. A current challenger must
    declare a separately trained model artifact, the governed training policy that
    authorized it, and a leakage audit.
    """
    errors: list[str] = []
    required = (
        "provider",
        "provider_version",
        "scoring_rules_version",
        "source_snapshot",
        "target_gameweek",
        "training_max_gameweek",
        "training_policy_version",
        "minimum_exact_rule_gameweeks",
        "exact_rule_gameweeks",
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

    policy_version = str(manifest.get("training_policy_version", "")).strip()
    if not policy_version:
        errors.append("OpenFPL training policy version is empty")
    try:
        minimum_exact = int(manifest.get("minimum_exact_rule_gameweeks"))
        exact_gameweeks = tuple(int(value) for value in manifest.get("exact_rule_gameweeks", ()))
        readiness = exact_rule_history_readiness(
            exact_gameweeks,
            target_gameweek=target_gameweek,
            minimum_exact_rule_gameweeks=minimum_exact,
        )
        if not readiness["training_ready"]:
            errors.extend(f"OpenFPL training readiness: {reason}" for reason in readiness["reasons"])
        unique_exact = tuple(sorted(set(exact_gameweeks)))
        if unique_exact and training_max != max(unique_exact):
            errors.append(
                "training_max_gameweek does not match the maximum declared exact-rule gameweek"
            )
    except (TypeError, ValueError) as exc:
        errors.append(f"invalid OpenFPL training policy/history declaration: {exc}")

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
