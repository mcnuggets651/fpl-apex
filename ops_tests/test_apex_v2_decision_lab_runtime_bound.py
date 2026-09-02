from __future__ import annotations

import ast
import inspect
import re
import unittest
from pathlib import Path

from apex.decision import transfers as frozen_transfers


ORCHESTRATION_HEADROOM_SECONDS = 15 * 60


def _literal_int(node: ast.AST, *, label: str) -> int:
    if not isinstance(node, ast.Constant) or not isinstance(node.value, int):
        raise AssertionError(f"{label} must remain a literal integer for static runtime auditing")
    return int(node.value)


def _frozen_optimizer_runtime_contract() -> tuple[int, int, int]:
    source = inspect.getsource(frozen_transfers.optimise_transfer_horizon)
    function = ast.parse(source).body[0]
    if not isinstance(function, ast.FunctionDef):
        raise AssertionError("optimise_transfer_horizon did not parse as a function")

    kw_defaults = {
        arg.arg: default
        for arg, default in zip(function.args.kwonlyargs, function.args.kw_defaults, strict=True)
        if default is not None
    }
    candidate_limit = _literal_int(
        kw_defaults["candidate_limit"], label="candidate_limit default"
    )

    solve_function = next(
        (
            node
            for node in function.body
            if isinstance(node, ast.FunctionDef) and node.name == "solve"
        ),
        None,
    )
    if solve_function is None:
        raise AssertionError("frozen optimiser no longer has the audited local solve function")

    time_limits: list[int] = []
    for node in ast.walk(solve_function):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "milp":
            continue
        options = next((kw.value for kw in node.keywords if kw.arg == "options"), None)
        if not isinstance(options, ast.Dict):
            raise AssertionError("milp options must remain a literal mapping for runtime auditing")
        for key, value in zip(options.keys, options.values, strict=True):
            if isinstance(key, ast.Constant) and key.value == "time_limit":
                time_limits.append(_literal_int(value, label="MILP time_limit"))
    if len(time_limits) != 1:
        raise AssertionError(f"expected exactly one audited MILP time_limit, found {time_limits}")
    per_milp_time_limit = time_limits[0]

    candidate_loops = [
        node
        for node in function.body
        if isinstance(node, ast.For)
        and any(
            isinstance(child, ast.Name) and child.id == "candidate_limit"
            for child in ast.walk(node.iter)
        )
    ]
    if len(candidate_loops) != 1:
        raise AssertionError(
            "candidate generation loop shape changed; re-audit the exact optimiser call bound"
        )
    candidate_loop = candidate_loops[0]

    def is_solve_call(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "solve"
        )

    all_solve_calls = sum(1 for node in ast.walk(function) if is_solve_call(node))
    loop_solve_calls = sum(1 for node in ast.walk(candidate_loop) if is_solve_call(node))
    outside_loop_calls = all_solve_calls - loop_solve_calls
    if (outside_loop_calls, loop_solve_calls) != (1, 2):
        raise AssertionError(
            "optimiser solve-call shape changed; re-audit the runtime formula before shipping"
        )

    maximum_solver_calls = outside_loop_calls + candidate_limit * loop_solve_calls
    return candidate_limit, per_milp_time_limit, maximum_solver_calls


def _decision_lab_solve_timeout_minutes() -> int:
    workflow = Path(".github/workflows/apex-v2-decision-quality.yml").read_text(
        encoding="utf-8"
    )
    solve_job = re.search(
        r"(?ms)^  solve:\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:\n)", workflow
    )
    if solve_job is None:
        raise AssertionError("decision-quality workflow solve job not found")
    timeout = re.search(
        r"(?m)^    timeout-minutes:\s*(?P<minutes>\d+)\s*$",
        solve_job.group("body"),
    )
    if timeout is None:
        raise AssertionError("decision-quality solve job has no literal timeout-minutes")
    return int(timeout.group("minutes"))


class DecisionLabRuntimeBoundTests(unittest.TestCase):
    def test_frozen_optimizer_current_theoretical_solver_allowance_is_34_minutes(self):
        candidate_limit, per_milp_time_limit, maximum_solver_calls = (
            _frozen_optimizer_runtime_contract()
        )
        self.assertEqual(candidate_limit, 8)
        self.assertEqual(per_milp_time_limit, 120)
        self.assertEqual(maximum_solver_calls, 17)
        self.assertEqual(maximum_solver_calls * per_milp_time_limit, 34 * 60)

    def test_matrix_timeout_covers_frozen_solver_bound_plus_orchestration_headroom(self):
        _, per_milp_time_limit, maximum_solver_calls = _frozen_optimizer_runtime_contract()
        solver_allowance_seconds = maximum_solver_calls * per_milp_time_limit
        minimum_job_seconds = solver_allowance_seconds + ORCHESTRATION_HEADROOM_SECONDS
        workflow_seconds = _decision_lab_solve_timeout_minutes() * 60
        self.assertGreaterEqual(
            workflow_seconds,
            minimum_job_seconds,
            msg=(
                "decision-quality solve timeout is incompatible with the frozen exact optimiser: "
                f"solver_allowance={solver_allowance_seconds}s, "
                f"orchestration_headroom={ORCHESTRATION_HEADROOM_SECONDS}s, "
                f"required={minimum_job_seconds}s, configured={workflow_seconds}s"
            ),
        )


if __name__ == "__main__":
    unittest.main()
