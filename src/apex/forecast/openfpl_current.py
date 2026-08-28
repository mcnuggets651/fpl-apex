from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

CURRENT_SCORING_RULES_VERSION = "fpl-2026-27-v1"
CURRENT_EXACT_RULE_SEASON = "2026-27"
CURRENT_TRAINING_POLICY_VERSION = "openfpl-current-training-v1"
CURRENT_FEATURE_CONTRACT_VERSION = "openfpl-current-nonscore-v1"
CURRENT_MINIMUM_EXACT_RULE_GAMEWEEKS = 10
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

# The published OpenFPL sample matrix contains rolling FPL points, BPS and bonus
# columns. Those observations encode the scoring rules of the season in which they
# were generated, so they may not enter the current-rules feature matrix.
SCORE_DEPENDENT_REFERENCE_FEATURE_FAMILIES = (
    "player fpl points",
    "player relevant fpl points",
    "player bps",
    "player fpl bonus points",
)


def _normalise_feature_name(value: Any) -> str:
    return " ".join(str(value).strip().casefold().replace("_", " ").split())


def score_dependent_feature_columns(columns: Iterable[Any]) -> tuple[str, ...]:
    """Return reference columns that encode legacy FPL scoring outcomes."""
    banned = tuple(_normalise_feature_name(value) for value in SCORE_DEPENDENT_REFERENCE_FEATURE_FAMILIES)
    found: list[str] = []
    for raw in columns:
        name = str(raw)
        normalised = _normalise_feature_name(raw)
        if any(
            normalised == prefix or normalised.startswith(prefix + " ")
            for prefix in banned
        ):
            found.append(name)
    return tuple(found)


def training_policy_sha256(policy: dict[str, Any]) -> str:
    payload = json.dumps(
        policy,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def training_policy_errors(policy: dict[str, Any]) -> tuple[str, ...]:
    """Validate the governed OpenFPL current-rules training constitution."""
    errors: list[str] = []
    if int(policy.get("schema_version", -1)) != 1:
        errors.append("OpenFPL training policy schema_version must be 1")
    if str(policy.get("policy_version", "")) != CURRENT_TRAINING_POLICY_VERSION:
        errors.append(
            f"OpenFPL training policy must be {CURRENT_TRAINING_POLICY_VERSION}"
        )
    if str(policy.get("season", "")) != "2026-2027":
        errors.append("OpenFPL training policy season must be 2026-2027")
    if str(policy.get("exact_rule_season", "")) != CURRENT_EXACT_RULE_SEASON:
        errors.append(
            f"OpenFPL exact-rule season must be {CURRENT_EXACT_RULE_SEASON}"
        )
    if str(policy.get("scoring_rules_version", "")) != CURRENT_SCORING_RULES_VERSION:
        errors.append(
            f"OpenFPL training policy scoring must be {CURRENT_SCORING_RULES_VERSION}"
        )
    if str(policy.get("feature_contract_version", "")) != CURRENT_FEATURE_CONTRACT_VERSION:
        errors.append(
            f"OpenFPL feature contract must be {CURRENT_FEATURE_CONTRACT_VERSION}"
        )
    try:
        minimum = int(policy.get("minimum_exact_rule_gameweeks"))
    except (TypeError, ValueError):
        minimum = -1
    if minimum != CURRENT_MINIMUM_EXACT_RULE_GAMEWEEKS:
        errors.append(
            "OpenFPL governed exact-rule history floor must be "
            f"{CURRENT_MINIMUM_EXACT_RULE_GAMEWEEKS} gameweeks"
        )
    label_seasons = tuple(map(str, policy.get("training_label_seasons", ())))
    if label_seasons != (CURRENT_EXACT_RULE_SEASON,):
        errors.append("OpenFPL current labels must come only from 2026-27")
    if policy.get("historical_context_allowed") is not True:
        errors.append("OpenFPL policy must explicitly govern historical context")
    if policy.get("historical_context_must_be_score_independent") is not True:
        errors.append("OpenFPL historical context must be score-independent")

    exclusions = {
        _normalise_feature_name(value)
        for value in policy.get("excluded_score_dependent_feature_families", ())
    }
    required_exclusions = {
        _normalise_feature_name(value)
        for value in SCORE_DEPENDENT_REFERENCE_FEATURE_FAMILIES
    }
    missing = sorted(required_exclusions - exclusions)
    if missing:
        errors.append(
            "OpenFPL policy does not exclude all legacy scoring feature families: "
            + ", ".join(missing)
        )

    windows = tuple(int(value) for value in policy.get("reference_rolling_windows", ()))
    if windows != REFERENCE_ROLLING_WINDOWS:
        errors.append(
            "OpenFPL policy rolling-window contract does not match the pinned reference"
        )

    model = policy.get("model_contract") or {}
    positions = tuple(map(str, model.get("positions", ())))
    if positions != ("GK", "DEF", "MID", "FWD"):
        errors.append("OpenFPL current model positions must be GK/DEF/MID/FWD")
    if model.get("team_grouped_cross_validation") is not True:
        errors.append("OpenFPL current model must use team-grouped cross-validation")
    try:
        folds = int(model.get("cross_validation_folds"))
    except (TypeError, ValueError):
        folds = -1
    if folds != 5:
        errors.append("OpenFPL current model must use five cross-validation folds")
    if model.get("legacy_reference_weights_reused") is not False:
        errors.append("OpenFPL current policy must prohibit legacy reference weights")
    if model.get("placeholder_invariance_required") is not True:
        errors.append("OpenFPL current policy must require placeholder invariance")
    try:
        coverage = float(model.get("official_decision_universe_coverage_required"))
    except (TypeError, ValueError):
        coverage = -1.0
    if abs(coverage - 1.0) > 1e-12:
        errors.append("OpenFPL current policy must require 100% Official coverage")
    if model.get("serve_authorized") is not False:
        errors.append("OpenFPL current training policy must remain non-serving")
    return tuple(dict.fromkeys(errors))


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
    """Describe OpenFPL exact-rule label-history readiness.

    A caller that has not loaded a governed policy may still pass ``None`` and gets a
    fail-closed TRAINING_POLICY_UNSET result. Production readiness loads the versioned
    policy file and passes its approved floor explicitly.
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
                "was supplied"
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
    expected_training_policy_sha256: str | None = None,
) -> tuple[str, ...]:
    """Fail closed unless an OpenFPL adaptation is genuinely current and leakage-safe."""
    errors: list[str] = []
    required = (
        "provider",
        "provider_version",
        "scoring_rules_version",
        "source_snapshot",
        "target_gameweek",
        "training_max_gameweek",
        "training_policy_version",
        "training_policy_sha256",
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
    if policy_version != CURRENT_TRAINING_POLICY_VERSION:
        errors.append(
            f"OpenFPL training policy version must be {CURRENT_TRAINING_POLICY_VERSION}"
        )
    policy_digest = str(manifest.get("training_policy_sha256", "")).lower()
    if len(policy_digest) != 64 or any(ch not in "0123456789abcdef" for ch in policy_digest):
        errors.append("training_policy_sha256 must be a SHA-256 hex digest")
    if (
        expected_training_policy_sha256 is not None
        and policy_digest != str(expected_training_policy_sha256).lower()
    ):
        errors.append("OpenFPL training model is bound to a different governed policy hash")

    try:
        minimum_exact = int(manifest.get("minimum_exact_rule_gameweeks"))
        if minimum_exact != CURRENT_MINIMUM_EXACT_RULE_GAMEWEEKS:
            errors.append(
                "OpenFPL model minimum exact-rule history must equal governed floor "
                f"{CURRENT_MINIMUM_EXACT_RULE_GAMEWEEKS}"
            )
        exact_gameweeks = tuple(int(value) for value in manifest.get("exact_rule_gameweeks", ()))
        readiness = exact_rule_history_readiness(
            exact_gameweeks,
            target_gameweek=target_gameweek,
            minimum_exact_rule_gameweeks=minimum_exact,
        )
        if not readiness["training_ready"]:
            errors.extend(
                f"OpenFPL training readiness: {reason}" for reason in readiness["reasons"]
            )
        unique_exact = tuple(sorted(set(exact_gameweeks)))
        if unique_exact and training_max != max(unique_exact):
            errors.append(
                "training_max_gameweek does not match the maximum declared exact-rule gameweek"
            )
    except (TypeError, ValueError) as exc:
        errors.append(f"invalid OpenFPL training policy/history declaration: {exc}")

    if str(manifest.get("feature_contract_version", "")) != CURRENT_FEATURE_CONTRACT_VERSION:
        errors.append(
            f"OpenFPL feature contract must be {CURRENT_FEATURE_CONTRACT_VERSION}"
        )
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
    for key in ("model_artifact_sha256", "training_dataset_sha256"):
        value = str(manifest.get(key, "")).lower()
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            errors.append(f"{key} must be a SHA-256 hex digest")
    return tuple(dict.fromkeys(errors))
