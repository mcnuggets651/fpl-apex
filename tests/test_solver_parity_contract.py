import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_refresh_core_installs_project_before_validation_and_invalidation():
    workflow = (ROOT / ".github/workflows/refresh-core-pin.yml").read_text(
        encoding="utf-8"
    )
    install = "python -m pip install -e ."
    import_check = (
        'python -c "from apex_fpl.services.publication import '
        "invalidate_published_decision; print('apex package import ok')\""
    )
    assert install in workflow
    assert import_check in workflow
    assert workflow.index(install) < workflow.index(
        "python scripts/validate_core_candidate.py"
    )
    assert workflow.index(install) < workflow.index(
        "python scripts/check_upstreams.py"
    )
    assert workflow.index(install) < workflow.index(
        "python scripts/invalidate_published_decision.py"
    )


def test_external_solver_uses_same_approximate_pinnacle_objective():
    apex = yaml.safe_load((ROOT / "config/apex.yaml").read_text(encoding="utf-8"))
    parity = json.loads(
        (ROOT / "config/open_solver_parity.json").read_text(encoding="utf-8")
    )
    workflow = (ROOT / ".github/workflows/pinnacle.yml").read_text(encoding="utf-8")

    assert parity["preseason"] is True
    assert parity["objective"] == "decay"
    assert parity["decay_base"] == apex["fixture_decay"]
    assert set(parity["bench_weights"].values()) == {
        apex["approximate_bench_weight"]
    }
    assert parity["vcap_weight"] == 0.0
    assert parity["itb_value"] == 0.0
    assert parity["ft_value"] == 0.0
    assert parity["ft_value_list"] == {}
    assert parity["no_transfer_gws"] == list(range(2, apex["horizon"] + 1))
    assert parity["xmin_lb"] == 0
    assert parity["ev_per_price_cutoff"] == 0
    assert parity["keep_top_ev_percent"] == 100
    assert 'config/open_solver_parity.json' in workflow
