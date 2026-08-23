from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

from apex_fpl.services.release_profile import INSEASON_SELECTOR


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "certify_release_generation.py"
SPEC = spec_from_file_location("certify_release_generation_observability", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_release_failure_is_persisted_as_structured_certificate(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    bundle_dir = tmp_path / "bundle"
    promotion_dir = tmp_path / "promotion"
    run_dir.mkdir()
    bundle_dir.mkdir()

    squad = list(range(1, 16))
    canonical = {
        "decision_bundle_id": "bundle",
        "recommendation": {
            "selector": INSEASON_SELECTOR,
            "current_gameweek": 2,
        },
    }
    manifest = {
        "bundle_id": "bundle",
        "gameweeks": [2, 3],
        "team_state": {
            "configured": True,
            "ok": True,
            "state": {
                "squad": squad,
                "published_gw": 1,
                "selling_prices_exact": True,
                "selling_prices": {str(pid): 5.0 for pid in squad},
            },
        },
    }
    (run_dir / "apex_recommendation_latest.json").write_text(json.dumps(canonical))
    (bundle_dir / "manifest.json").write_text(json.dumps(manifest))

    def fail_run(*args):
        raise RuntimeError("synthetic sensitivity failure")

    monkeypatch.setattr(MODULE, "_run", fail_run)
    certificate = MODULE.certify_generation(
        run_dir=run_dir,
        bundle_dir=bundle_dir,
        promotion_dir=promotion_dir,
        run_id="test-run",
    )

    persisted = json.loads((run_dir / "release_generation_certificate.json").read_text())
    assert certificate["ready"] is False
    assert persisted["ready"] is False
    assert persisted["lifecycle"] == "in_season_receding_horizon"
    assert persisted["gates"]["profile"] == "passed"
    assert persisted["gates"]["sensitivity"] == "pending"
    assert any("synthetic sensitivity failure" in row for row in persisted["blockers"])
