from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Mutation:
    name: str
    path: str
    needle: str
    replacement: str
    tests: tuple[str, ...]


MUTATIONS = (
    Mutation(
        "initial-budget-bypass",
        "src/apex/decision/validate.py",
        'budget = BUDGET_TENTHS if mode == "INITIAL_SQUAD" else None',
        "budget = None",
        (
            "tests/test_v2_adversarial_economics_and_state.py::test_initial_squad_over_100m_is_illegal_at_decision_boundary",
            "tests/test_v2_adversarial_economics_and_state.py::test_certification_cannot_authorize_over_budget_initial_squad",
        ),
    ),
    Mutation(
        "snapshot-identity-bypass",
        "src/apex/runtime/snapshot.py",
        "if recorded_snapshot_id != computed_snapshot_id:",
        "if False:",
        ("tests/test_v2_adversarial_snapshot_integrity.py::test_open_snapshot_recomputes_content_addressed_snapshot_identity",),
    ),
    Mutation(
        "publication-witness-bypass",
        "src/apex/runtime/publication.py",
        "    _assert_decision_witness(snapshot, decision)\n",
        "    pass  # MUTANT: witness verification disabled\n",
        (
            "tests/test_v2_adversarial_publication_binding.py::test_publication_rejects_tampered_certification_with_same_snapshot",
            "tests/test_v2_adversarial_publication_binding.py::test_publication_rejects_tampered_system_decision_with_same_snapshot",
        ),
    ),
    Mutation(
        "serving-string-bool-bypass",
        "src/apex/runtime/serving.py",
        '''        _strict_bool(\n            row.get("serve_authorized", False),\n            field=f"provider {row.get('provider_id', '<unknown>')} serve_authorized",\n        ),\n''',
        '''        bool(row.get("serve_authorized", False)),\n''',
        ("tests/test_v2_adversarial_publication_binding.py::test_serving_matrix_rejects_string_authorization_boolean",),
    ),
    Mutation(
        "nonfinite-freshness-bypass",
        "src/apex/runtime/config.py",
        "if not math.isfinite(max_age_hours) or max_age_hours <= 0:",
        "if max_age_hours <= 0:",
        ("tests/test_v2_adversarial_config_integrity.py::test_config_rejects_nonfinite_provider_max_age",),
    ),
    Mutation(
        "malformed-certification-clock-not-blocking",
        "src/apex/governance/certification.py",
        "            reasons.append(ReasonCode.SNAPSHOT_INCOHERENT)\n",
        "            pass  # MUTANT: malformed deadline does not block\n",
        ("tests/test_v2_adversarial_certification_clock.py::test_malformed_valid_until_fails_closed_instead_of_crashing",),
    ),
)


def _apply(root: Path, mutation: Mutation) -> None:
    path = root / mutation.path
    text = path.read_text(encoding="utf-8")
    count = text.count(mutation.needle)
    if count != 1:
        raise RuntimeError(
            f"mutation {mutation.name} expected exactly one target in {mutation.path}; found {count}"
        )
    path.write_text(text.replace(mutation.needle, mutation.replacement, 1), encoding="utf-8")


def _run(root: Path, mutation: Mutation) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *mutation.tests],
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def main() -> int:
    survivors = []
    with tempfile.TemporaryDirectory(prefix="apex-v2-mutation-") as raw_tmp:
        workspace = Path(raw_tmp)
        for index, mutation in enumerate(MUTATIONS, start=1):
            mutant_root = workspace / f"mutant-{index}"
            shutil.copytree(
                ROOT,
                mutant_root,
                ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", "artifacts", ".coverage"),
            )
            _apply(mutant_root, mutation)
            result = _run(mutant_root, mutation)
            if result.returncode == 0:
                survivors.append(mutation.name)
                print(f"SURVIVED {mutation.name}")
                print(result.stdout)
            else:
                print(f"KILLED {mutation.name}")
    if survivors:
        print("Mutation gate failed; surviving critical mutants: " + ", ".join(survivors))
        return 1
    print(f"Mutation gate passed: killed {len(MUTATIONS)}/{len(MUTATIONS)} critical mutants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
