from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "apply_joint_path_promotion.py"
SPEC = spec_from_file_location("apply_joint_path_promotion", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _result(*, status="optimal", stable=True, gain=0.30):
    return SimpleNamespace(
        status=status,
        candidate_pool_stable=stable,
        gain_vs_baseline=gain,
    )


def test_promotion_requires_predeclared_material_gain():
    gate = MODULE._promotion_gate(_result(gain=0.249))
    assert gate["joint_path_optimal"] is True
    assert gate["candidate_pool_stable"] is True
    assert gate["material_gain_vs_static"] is False
    assert gate["promotion_candidate"] is False


def test_promotion_requires_candidate_pool_stability():
    gate = MODULE._promotion_gate(_result(stable=False, gain=1.0))
    assert gate["material_gain_vs_static"] is True
    assert gate["candidate_pool_stable"] is False
    assert gate["promotion_candidate"] is False


def test_promotion_passes_at_declared_boundary():
    gate = MODULE._promotion_gate(_result(gain=0.25))
    assert gate == {
        "joint_path_optimal": True,
        "candidate_pool_stable": True,
        "material_gain_vs_static": True,
        "promotion_candidate": True,
    }


def test_promotion_requires_optimal_joint_solve():
    gate = MODULE._promotion_gate(_result(status="infeasible", gain=2.0))
    assert gate["joint_path_optimal"] is False
    assert gate["promotion_candidate"] is False
