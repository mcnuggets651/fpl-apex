from pathlib import Path


def test_stochastic_transfer_solver_is_not_yet_wired_into_serving_runtime() -> None:
    solve_source = Path("src/apex/runtime/solve.py").read_text(encoding="utf-8")

    assert "stochastic_transfers" not in solve_source
    assert "optimise_stochastic_transfer_policy" not in solve_source
