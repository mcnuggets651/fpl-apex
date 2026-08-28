from __future__ import annotations

from scripts.openfpl_reference_preflight import _reference_reproducibility


def test_reference_checkout_with_only_play_notebook_is_inference_only(tmp_path):
    (tmp_path / "README.md").write_text(
        "To use OpenFPL on custom data, you need to construct samples based on data "
        "from FPL and Understat APIs (see *data/samples.csv* and [paper](x) for inspiration).",
        encoding="utf-8",
    )
    (tmp_path / "play.ipynb").write_text(
        "samples_df = pd.read_csv('data/samples.csv')\n"
        "models = joblib.load('models/model.joblib')\n"
        "np.median(position_predictions, axis=0)\n",
        encoding="utf-8",
    )

    report = _reference_reproducibility(tmp_path)

    assert report["reference_reproducibility_scope"] == "INFERENCE_ONLY"
    assert report["reference_inference_state"] == "REFERENCE_INFERENCE_REPRODUCIBLE"
    assert report["training_pipeline_state"] == "TRAINING_PIPELINE_NOT_PUBLISHED"
    assert report["training_pipeline_published"] is False
    assert report["sample_construction_state"] == "SAMPLE_CONSTRUCTION_NOT_PUBLISHED"
    assert report["sample_construction_published"] is False
    assert report["readme_delegates_sample_construction"] is True
    assert report["published_code_inventory"] == ["play.ipynb"]
    assert report["provenance_contract"]["future_current_rules_identity"] == (
        "apex-openfpl-method-derivative"
    )
    assert report["provenance_contract"][
        "derivative_may_claim_exact_upstream_training_reproduction"
    ] is False


def test_new_upstream_training_source_forces_reaudit_instead_of_silent_acceptance(tmp_path):
    (tmp_path / "README.md").write_text(
        "To use OpenFPL on custom data, you need to construct samples based on data "
        "from FPL and Understat APIs (see *data/samples.csv* and [paper](x) for inspiration).",
        encoding="utf-8",
    )
    (tmp_path / "play.ipynb").write_text(
        "samples_df = pd.read_csv('data/samples.csv')\n"
        "models = joblib.load('models/model.joblib')\n"
        "np.median(position_predictions, axis=0)\n",
        encoding="utf-8",
    )
    (tmp_path / "train_models.py").write_text("model.fit(X, y)\n", encoding="utf-8")

    report = _reference_reproducibility(tmp_path)

    assert report["reference_reproducibility_scope"] == (
        "TRAINING_SOURCE_PRESENT_REQUIRES_AUDIT"
    )
    assert report["training_pipeline_state"] == "TRAINING_SOURCE_PRESENT_REQUIRES_AUDIT"
    assert report["training_pipeline_published"] is True
    assert report["published_training_source_candidates"] == ["train_models.py"]
    # The README still delegates sample construction, so a model-training script alone
    # must not be mistaken for a complete reproducible sample-construction pipeline.
    assert report["sample_construction_published"] is False


def test_training_logic_hidden_in_play_notebook_is_detected_for_reaudit(tmp_path):
    (tmp_path / "README.md").write_text("custom data", encoding="utf-8")
    (tmp_path / "play.ipynb").write_text(
        "samples_df = pd.read_csv('data/samples.csv')\n"
        "models = joblib.load('models/model.joblib')\n"
        "np.median(position_predictions, axis=0)\n"
        "KBinsDiscretizer()\n"
        "model.fit(X, y)\n",
        encoding="utf-8",
    )

    report = _reference_reproducibility(tmp_path)

    assert report["training_pipeline_published"] is True
    assert report["reference_reproducibility_scope"] == (
        "TRAINING_SOURCE_PRESENT_REQUIRES_AUDIT"
    )
    assert "KBinsDiscretizer" in report["training_markers_present"]
    assert ".fit(" in report["training_markers_present"]
