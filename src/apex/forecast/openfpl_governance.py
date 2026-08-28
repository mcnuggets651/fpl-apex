from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

README_CUSTOM_SAMPLE_MARKERS = (
    "you need to construct samples based on data from FPL and Understat APIs",
    "see *data/samples.csv* and [paper]",
)
INFERENCE_NOTEBOOK_MARKERS = (
    "samples_df = pd.read_csv",
    "joblib.load",
    "np.median(position_predictions, axis=0)",
)
TRAINING_NOTEBOOK_MARKERS = (
    ".fit(",
    "GridSearchCV",
    "KBestSearch",
    "KBinsDiscretizer",
    "compute_sample_weight",
)


def governance_mapping_sha256(payload: dict[str, Any]) -> str:
    """Hash governed semantic content independently of YAML formatting/order."""
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def method_contract_sha256(contract: dict[str, Any]) -> str:
    """Return the canonical identity digest for an OpenFPL method contract."""
    return governance_mapping_sha256(contract)


def published_code_inventory(root: Path) -> list[str]:
    """Return executable/notebook source files published by the pinned reference."""
    suffixes = {".py", ".ipynb", ".r", ".R", ".jl"}
    return sorted(
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and path.suffix in suffixes
    )


def reference_reproducibility(root: Path) -> dict[str, Any]:
    """Classify what the pinned OpenFPL release actually makes reproducible.

    This intentionally distinguishes released inference from unpublished sample-
    construction/training source. A later upstream source addition forces re-audit
    instead of being silently accepted as equivalent to the currently pinned release.
    """
    readme = (
        (root / "README.md").read_text(encoding="utf-8")
        if (root / "README.md").is_file()
        else ""
    )
    notebook = (
        (root / "play.ipynb").read_text(encoding="utf-8")
        if (root / "play.ipynb").is_file()
        else ""
    )
    inventory = published_code_inventory(root)
    readme_delegates_sample_construction = all(
        marker in readme for marker in README_CUSTOM_SAMPLE_MARKERS
    )
    inference_markers_present = all(
        marker in notebook for marker in INFERENCE_NOTEBOOK_MARKERS
    )
    training_markers_present = [
        marker for marker in TRAINING_NOTEBOOK_MARKERS if marker in notebook
    ]
    published_training_sources = [
        path
        for path in inventory
        if path != "play.ipynb"
        and any(
            token in path.casefold()
            for token in ("train", "feature", "sample", "data")
        )
    ]

    pipeline_published = bool(published_training_sources or training_markers_present)
    sample_construction_published = bool(
        published_training_sources and not readme_delegates_sample_construction
    )
    if pipeline_published:
        scope = "TRAINING_SOURCE_PRESENT_REQUIRES_AUDIT"
        pipeline_state = "TRAINING_SOURCE_PRESENT_REQUIRES_AUDIT"
    else:
        scope = "INFERENCE_ONLY"
        pipeline_state = "TRAINING_PIPELINE_NOT_PUBLISHED"

    return {
        "reference_reproducibility_scope": scope,
        "reference_inference_state": (
            "REFERENCE_INFERENCE_REPRODUCIBLE"
            if inference_markers_present
            else "REFERENCE_INFERENCE_CONTRACT_CHANGED"
        ),
        "training_pipeline_state": pipeline_state,
        "training_pipeline_published": pipeline_published,
        "sample_construction_state": (
            "SAMPLE_CONSTRUCTION_PUBLISHED_REQUIRES_AUDIT"
            if sample_construction_published
            else "SAMPLE_CONSTRUCTION_NOT_PUBLISHED"
        ),
        "sample_construction_published": sample_construction_published,
        "readme_delegates_sample_construction": readme_delegates_sample_construction,
        "published_code_inventory": inventory,
        "published_training_source_candidates": published_training_sources,
        "inference_markers_present": inference_markers_present,
        "training_markers_present": training_markers_present,
        "provenance_contract": {
            "exact_upstream_reference_identity": "openfpl-reference-inference",
            "future_current_rules_identity": "apex-openfpl-method-derivative",
            "derivative_may_claim_exact_upstream_training_reproduction": False,
            "reason": (
                "The pinned upstream publishes trained models and inference code, "
                "while its README delegates custom sample construction to users. "
                "A current-rules implementation derived from the paper must therefore "
                "carry a distinct provenance identity unless upstream later publishes "
                "the missing construction/training source."
            ),
        },
    }


def validate_method_contract(
    contract: dict[str, Any],
    policy: dict[str, Any],
    locks: dict[str, Any],
) -> tuple[str, ...]:
    """Validate the governed Apex OpenFPL-method derivative constitution."""
    errors: list[str] = []

    if contract.get("schema_version") != 1:
        errors.append("method contract schema_version must be 1")
    if contract.get("contract_id") != "apex-openfpl-method-derivative-v1":
        errors.append("unexpected method contract_id")
    if contract.get("provider_family") != "openfpl":
        errors.append("provider_family must remain openfpl")
    if contract.get("implementation_id") != "apex-openfpl-method-derivative":
        errors.append("current implementation must carry derivative identity")
    if contract.get("upstream_reference_identity") != "openfpl-reference-inference":
        errors.append("upstream reference identity must remain inference-only")
    if contract.get("exact_upstream_training_reproduction_claim") is not False:
        errors.append("derivative cannot claim exact upstream training reproduction")

    upstream = locks["sources"]["openfpl"]
    if contract.get("upstream_repository") != upstream.get("repository"):
        errors.append("method contract OpenFPL repository differs from upstream lock")
    if contract.get("upstream_commit") != upstream.get("commit"):
        errors.append("method contract OpenFPL commit differs from upstream lock")

    provenance = contract.get("provenance") or {}
    for key in (
        "upstream_publishes_trained_models",
        "upstream_publishes_inference_code",
        "upstream_publishes_sample_matrix",
    ):
        if provenance.get(key) is not True:
            errors.append(f"provenance {key} must be true for pinned reference")
    for key in (
        "upstream_publishes_sample_construction_pipeline",
        "upstream_publishes_training_pipeline",
    ):
        if provenance.get(key) is not False:
            errors.append(
                f"provenance {key} must remain false until separately audited"
            )
    if provenance.get("reference_sample_equivalence_required_before_model_build") is not True:
        errors.append("reference sample equivalence must gate model construction")
    independent = provenance.get("independent_semantics_reference") or {}
    dastan = locks["sources"]["dastan"]
    if independent.get("repository") != dastan.get("repository"):
        errors.append(
            "independent semantics reference repository differs from Dastan lock"
        )
    if independent.get("commit") != dastan.get("commit"):
        errors.append("independent semantics reference commit differs from Dastan lock")
    if independent.get("authority") != "non_authoritative_cross_check_only":
        errors.append("Dastan semantics reference must remain non-authoritative")

    if contract.get("scoring_rules_version") != policy.get("scoring_rules_version"):
        errors.append("method and training policy scoring-rules versions differ")
    if contract.get("feature_contract_version") != policy.get("feature_contract_version"):
        errors.append("method and training policy feature-contract versions differ")

    windows = tuple(
        int(value) for value in (contract.get("history") or {}).get("windows", ())
    )
    policy_windows = tuple(
        int(value) for value in policy.get("reference_rolling_windows", ())
    )
    if windows != (1, 3, 5, 10, 38):
        errors.append("method rolling windows must be exactly 1/3/5/10/38")
    if windows != policy_windows:
        errors.append("method rolling windows differ from governed training policy")
    history = contract.get("history") or {}
    if (
        history.get("current_match_excluded") is not True
        or history.get("shift_completed_matches") != 1
    ):
        errors.append(
            "rolling history must exclude the current match with a one-match shift"
        )
    if history.get("aggregation") != "arithmetic_mean":
        errors.append("OpenFPL method history aggregation must be arithmetic mean")
    if history.get("future_placeholder_invariance_required") is not True:
        errors.append("future-placeholder invariance must be required")

    excluded = tuple(
        contract.get("excluded_score_dependent_player_families", ())
    )
    policy_excluded = tuple(
        str(value).removeprefix("player ")
        for value in policy.get("excluded_score_dependent_feature_families", ())
    )
    if set(excluded) != set(policy_excluded):
        errors.append("method score-dependent exclusions differ from training policy")

    player = contract.get("player_families") or {}
    common = tuple(player.get("common_current", ()))
    goalkeeper = tuple(player.get("goalkeeper_only", ()))
    field = tuple(player.get("field_only", ()))
    for banned in excluded:
        if banned in common or banned in goalkeeper or banned in field:
            errors.append(
                f"banned scoring-dependent feature remains active: {banned}"
            )

    team_count = len(contract.get("team_families_current", ()))
    opponent_count = len(contract.get("opponent_families_current", ()))
    if team_count != 10 or opponent_count != 10:
        errors.append(
            "current GK/field team and opponent family counts must both be 10"
        )
    position_contract = contract.get("position_feature_contract") or {}
    expected_player_counts = {
        "GK": len(common) + len(goalkeeper),
        "DEF": len(common) + len(field),
        "MID": len(common) + len(field),
        "FWD": len(common) + len(field),
    }
    for position, player_count in expected_player_counts.items():
        row = position_contract.get(position) or {}
        if row.get("player_family_count") != player_count:
            errors.append(f"{position} player family count is inconsistent")
        if row.get("team_family_count") != team_count:
            errors.append(f"{position} team family count is inconsistent")
        if row.get("opponent_family_count") != opponent_count:
            errors.append(f"{position} opponent family count is inconsistent")
        status_count = len(row.get("status_features", ()))
        expected_features = (
            (player_count + team_count + opponent_count) * len(windows)
            + status_count
        )
        if row.get("current_feature_count") != expected_features:
            errors.append(
                f"{position} feature count must be {expected_features}, got "
                f"{row.get('current_feature_count')}"
            )

    reference = contract.get("reference_sample_matrix") or {}
    identifiers = len(reference.get("identifier_columns", ()))
    statuses = len(reference.get("status_columns", ()))
    rolling = int(reference.get("rolling_feature_columns", -1))
    if identifiers + statuses + rolling != int(reference.get("total_columns", -1)):
        errors.append("reference sample matrix column accounting is inconsistent")
    if int(reference.get("total_columns", -1)) != 235:
        errors.append("pinned OpenFPL reference sample must remain 235 columns")
    reference_family_total = (
        int(reference.get("player_rolling_family_count", -1))
        + int(reference.get("team_rolling_family_count", -1))
        + int(reference.get("opponent_rolling_family_count", -1))
    )
    if reference_family_total * len(windows) != rolling:
        errors.append("reference rolling-family accounting is inconsistent")

    training = contract.get("training") or {}
    if tuple(training.get("positions", ())) != ("GK", "DEF", "MID", "FWD"):
        errors.append("current derivative positions must be GK/DEF/MID/FWD")
    cross_validation = training.get("cross_validation") or {}
    if (
        cross_validation.get("folds") != 5
        or cross_validation.get("grouping") != "Premier League team"
    ):
        errors.append("training must retain five team-grouped folds")
    bins = (training.get("sample_weighting") or {}).get("bins") or {}
    if bins != {"GK": 2, "DEF": 3, "MID": 4, "FWD": 3}:
        errors.append("position sample-weight bins differ from paper method")
    search = training.get("search") or {}
    if (
        search.get("algorithm") != "K-Best Search"
        or search.get("population_size") != 10
    ):
        errors.append("K-Best Search population must remain 10")
    ensemble = training.get("ensemble") or {}
    if ensemble.get("top_models_per_fold") != 10 or ensemble.get("folds") != 5:
        errors.append("ensemble must retain top-10 models across five folds")
    if (
        ensemble.get("individual_models_per_position") != 50
        or ensemble.get("aggregation") != "median"
    ):
        errors.append("ensemble must be median of 50 models per position")

    gates = contract.get("build_gates") or {}
    if gates.get("governed_training_policy") != policy.get("policy_version"):
        errors.append("method contract points to a different training policy")
    if gates.get("minimum_completed_exact_rule_gameweeks") != policy.get(
        "minimum_exact_rule_gameweeks"
    ):
        errors.append("method and policy minimum exact-rule gameweeks differ")
    if gates.get("model_build_before_history_gate") != "forbidden":
        errors.append("model build must be forbidden before history gate")
    if gates.get("serve_authorized") is not False:
        errors.append("method contract cannot authorize serving")
    if gates.get("prospective_qualification_required_for_serving") is not True:
        errors.append("prospective qualification must remain required")

    return tuple(dict.fromkeys(errors))
