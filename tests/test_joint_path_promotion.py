from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "apply_joint_path_promotion.py"
SPEC = spec_from_file_location("apply_joint_path_promotion", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _result(*, status="optimal", stable=True, within=True):
    return SimpleNamespace(
        status=status,
        candidate_pool_stable=stable,
        selected=SimpleNamespace(within_gw1_band=within),
    )


def test_launch_gate_requires_gw1_floor() -> None:
    gate = MODULE._launch_gate(_result(within=False))
    assert gate["gw1_first_optimal"] is True
    assert gate["candidate_pool_stable"] is True
    assert gate["gw1_floor_respected"] is False
    assert gate["promotion_candidate"] is False


def test_launch_gate_requires_candidate_stability() -> None:
    gate = MODULE._launch_gate(_result(stable=False))
    assert gate["gw1_floor_respected"] is True
    assert gate["candidate_pool_stable"] is False
    assert gate["promotion_candidate"] is False


def test_launch_gate_has_no_material_eight_week_gain_requirement() -> None:
    gate = MODULE._launch_gate(_result())
    assert gate == {
        "gw1_first_optimal": True,
        "candidate_pool_stable": True,
        "gw1_floor_respected": True,
        "promotion_candidate": True,
    }


def test_launch_gate_requires_optimal_gw1_solve() -> None:
    gate = MODULE._launch_gate(_result(status="infeasible"))
    assert gate["gw1_first_optimal"] is False
    assert gate["promotion_candidate"] is False
