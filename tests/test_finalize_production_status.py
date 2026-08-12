import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path(__file__).parents[1] / "scripts" / "finalize_production_status.py"


def test_early_failure_replaces_actionable_contract_and_rejects_stale_diagnostics(tmp_path):
    generated = tmp_path / "generated"
    bundle = generated / "decision_bundle"
    archive = tmp_path / "history"
    reports = tmp_path / "reports"
    bundle.mkdir(parents=True)
    reports.mkdir()
    manifest = {
        "contract": "apex-decision-bundle-v1",
        "bundle_id": "fresh-bundle",
        "created_at": "2026-08-11T17:24:59+00:00",
        "identity": {
            "official": {"bootstrap_sha256": "boot", "fixtures_sha256": "fix"},
            "material_inputs": {"official_players": {"rows": 577}},
        },
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    (generated / "apex_recommendation_latest.json").write_text(
        json.dumps({"ready_to_act": True, "decision_bundle_id": "stale-bundle"})
    )
    for name in ("pinnacle_latest.json", "solver_parity.json", "elite_latest.json"):
        (generated / name).write_text(json.dumps({"decision_bundle_id": "stale-bundle"}))

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output-dir",
            str(generated),
            "--bundle-dir",
            str(bundle),
            "--archive-dir",
            str(archive),
            "--run-id",
            "75",
        ],
        cwd=tmp_path,
        check=True,
    )

    canonical = json.loads((generated / "apex_recommendation_latest.json").read_text())
    answer = json.loads((generated / "apex_answer_context.json").read_text())
    record = json.loads((archive / "fresh-bundle.json").read_text())
    assert canonical["ready_to_act"] is False
    assert canonical["recommendation"] is None
    assert canonical["decision_bundle_id"] == "fresh-bundle"
    assert answer["safe_to_act"] is False
    assert record["decision_bundle_id"] == "fresh-bundle"
    assert set(record["rejected_stale_diagnostics"]) == {
        "pinnacle_latest.json",
        "solver_parity.json",
        "elite_latest.json",
    }
    assert not (generated / "pinnacle_latest.json").exists()


def test_current_canonical_is_not_replaced(tmp_path):
    generated = tmp_path / "generated"
    bundle = generated / "decision_bundle"
    bundle.mkdir(parents=True)
    (bundle / "manifest.json").write_text(
        json.dumps({"bundle_id": "same", "created_at": "2026-08-11T17:00:00+00:00"})
    )
    expected = {"ready_to_act": True, "decision_bundle_id": "same"}
    (generated / "apex_recommendation_latest.json").write_text(json.dumps(expected))
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output-dir",
            str(generated),
            "--bundle-dir",
            str(bundle),
            "--canonical-step-succeeded",
        ],
        cwd=tmp_path,
        check=True,
    )
    assert json.loads((generated / "apex_recommendation_latest.json").read_text()) == expected


def test_matching_old_contract_is_replaced_when_canonical_step_failed(tmp_path):
    generated = tmp_path / "generated"
    bundle = generated / "decision_bundle"
    bundle.mkdir(parents=True)
    (bundle / "manifest.json").write_text(
        json.dumps({"bundle_id": "repeat", "created_at": "2026-08-11T18:00:00+00:00"})
    )
    (generated / "apex_recommendation_latest.json").write_text(
        json.dumps({"ready_to_act": True, "decision_bundle_id": "repeat"})
    )
    subprocess.run(
        [sys.executable, str(SCRIPT), "--output-dir", str(generated), "--bundle-dir", str(bundle)],
        cwd=tmp_path,
        check=True,
    )
    payload = json.loads((generated / "apex_recommendation_latest.json").read_text())
    assert payload["ready_to_act"] is False
    assert payload["recommendation"] is None


def test_current_pinnacle_blockers_are_preserved_in_canonical_not_ready(tmp_path):
    generated = tmp_path / "generated"
    bundle = generated / "decision_bundle"
    archive = tmp_path / "history"
    bundle.mkdir(parents=True)
    (bundle / "manifest.json").write_text(
        json.dumps({"bundle_id": "fresh", "created_at": "2026-08-12T09:14:00+00:00"})
    )
    (generated / "pinnacle_latest.json").write_text(
        json.dumps(
            {
                "decision_bundle_id": "fresh",
                "pinnacle_ready": False,
                "pinnacle_gate": {"blockers": ["Core coverage is incomplete"]},
            }
        )
    )

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output-dir",
            str(generated),
            "--bundle-dir",
            str(bundle),
            "--archive-dir",
            str(archive),
        ],
        cwd=tmp_path,
        check=True,
    )

    payload = json.loads((generated / "apex_recommendation_latest.json").read_text())
    assert "Core coverage is incomplete" in payload["blockers"]
    assert (generated / "pinnacle_latest.json").exists()
