#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path

from apex.forecast.openfpl_current import (
    CURRENT_SCORING_RULES_VERSION,
    REFERENCE_CV_FOLDS,
    REFERENCE_POSITIONS,
    REFERENCE_RUNTIME_DEPENDENCIES,
    REFERENCE_SCORING_RULES_VERSION,
    reference_asset_errors,
)

ROOT = Path(__file__).resolve().parents[1]

# The pinned upstream repository explicitly advertises models + inference code and
# tells users to construct custom samples themselves from FPL/Understat data. These
# markers let CI prove that we have not silently started treating an inference-only
# checkout as a published training pipeline.
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head(root: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
    ).strip()


def sample_header(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return next(csv.reader(handle))


def _published_code_inventory(root: Path) -> list[str]:
    suffixes = {".py", ".ipynb", ".r", ".R", ".jl"}
    return sorted(
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and path.suffix in suffixes
    )


def _reference_reproducibility(root: Path) -> dict:
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
    inventory = _published_code_inventory(root)
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
        and any(token in path.casefold() for token in ("train", "feature", "sample", "data"))
    ]

    pipeline_published = bool(published_training_sources or training_markers_present)
    sample_construction_published = bool(
        published_training_sources
        and not readme_delegates_sample_construction
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the pinned OpenFPL reference implementation without falsely "
            "qualifying its legacy model for current FPL scoring."
        )
    )
    parser.add_argument("--openfpl-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    openfpl_root = args.openfpl_root.resolve()
    lock = json.loads((ROOT / "upstreams.lock.json").read_text(encoding="utf-8"))[
        "sources"
    ]["openfpl"]
    expected_commit = str(lock["commit"])
    actual_commit = git_head(openfpl_root)

    errors = list(reference_asset_errors(openfpl_root))
    if actual_commit != expected_commit:
        errors.append(
            f"OpenFPL checkout commit mismatch: expected {expected_commit}, got {actual_commit}"
        )

    plug = tuple(
        line.strip()
        for line in (openfpl_root / "plug.txt").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ) if (openfpl_root / "plug.txt").is_file() else ()
    if plug != REFERENCE_RUNTIME_DEPENDENCIES:
        errors.append(
            "OpenFPL pinned runtime dependencies differ from the audited reference contract"
        )

    notebook = (
        (openfpl_root / "play.ipynb").read_text(encoding="utf-8")
        if (openfpl_root / "play.ipynb").is_file()
        else ""
    )
    required_notebook_markers = (
        "num_cvs = 5",
        "positions = ['GK', 'DEF', 'MID', 'FWD', 'AM']",
        "xscaler.save",
        "yscaler.save",
        "features.save",
        "np.median(position_predictions, axis=0)",
    )
    missing_markers = [marker for marker in required_notebook_markers if marker not in notebook]
    if missing_markers:
        errors.append(
            "OpenFPL reference notebook contract changed/missing markers: "
            + "; ".join(missing_markers)
        )

    samples = openfpl_root / "data" / "samples.csv"
    columns = sample_header(samples) if samples.is_file() else []
    if len(columns) < 200:
        errors.append(
            f"OpenFPL sample feature surface unexpectedly small: {len(columns)} columns"
        )

    reproducibility = _reference_reproducibility(openfpl_root)
    if reproducibility["reference_inference_state"] != "REFERENCE_INFERENCE_REPRODUCIBLE":
        errors.append("OpenFPL inference notebook markers are incomplete")
    # A missing training pipeline is an explicit governance blocker for exact upstream
    # retraining, not a failure of the published inference reference. Do not turn the
    # known upstream omission into a false CI failure.

    model_directories = [
        f"models/cv{fold}_{position}"
        for fold in REFERENCE_CV_FOLDS
        for position in REFERENCE_POSITIONS
    ]
    report = {
        "schema_version": 2,
        "provider": "openfpl",
        "repository": str(lock["repository"]),
        "expected_commit": expected_commit,
        "checkout_commit": actual_commit,
        "reference_assets_valid": not errors,
        "reference_errors": errors,
        "reference_scoring_rules_version": REFERENCE_SCORING_RULES_VERSION,
        "current_scoring_rules_version": CURRENT_SCORING_RULES_VERSION,
        "current_rules_compatible": False,
        "reference_runtime_dependencies": list(plug),
        "reference_cv_folds": list(REFERENCE_CV_FOLDS),
        "reference_positions": list(REFERENCE_POSITIONS),
        "reference_model_directories": model_directories,
        "sample_column_count": len(columns),
        "sample_schema_sha256": hashlib.sha256(
            "\n".join(columns).encode("utf-8")
        ).hexdigest(),
        "features_artifact_sha256": (
            sha256_file(openfpl_root / "models" / "features.save")
            if (openfpl_root / "models" / "features.save").is_file()
            else None
        ),
        "xscaler_artifact_sha256": (
            sha256_file(openfpl_root / "models" / "xscaler.save")
            if (openfpl_root / "models" / "xscaler.save").is_file()
            else None
        ),
        "yscaler_artifact_sha256": (
            sha256_file(openfpl_root / "models" / "yscaler.save")
            if (openfpl_root / "models" / "yscaler.save").is_file()
            else None
        ),
        "ensemble_contract": "five-fold position-specific models; median across loaded candidate predictions",
        **reproducibility,
        "serve_authorized": False,
        "predictive_status": "INSUFFICIENT_HISTORY",
        "qualification_blockers": [
            "LEGACY_SCORING_REFERENCE",
            "TRAINING_PIPELINE_NOT_PUBLISHED",
            "CURRENT_RULE_HISTORY_GATE",
            "PROSPECTIVE_QUALIFICATION_REQUIRED",
        ],
        "qualification_blocker": (
            "reference inference artifacts target legacy scoring/features; exact "
            "upstream sample-construction/training source is not published; a "
            "separately identified current-rules derivative plus leakage-safe live "
            "feature exporter and prospective qualification are required"
        ),
        "next_required_artifacts": [
            "current-rules chronological training dataset",
            "Apex OpenFPL-method derivative feature-construction manifest",
            "current-rules derivative model artifact manifest",
            "leakage-safe live feature exporter",
            "future-placeholder invariance proof",
            "100% Official DecisionUniverse H1 shadow export",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
