from __future__ import annotations

import json
import tempfile
from pathlib import Path

from apex.domain.models import dataclass_to_dict
from apex.runtime.snapshot import open_frozen_snapshot
from apex.runtime.solve import solve_snapshot

from . import publication_impl as _impl

# Preserve the established publication module API, including private helpers used by
# evaluator/reveal code and focused contract tests. Only the final build boundary is
# replaced by the replay-verifying facade below.
for _name in dir(_impl):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_impl, _name)


def replay_security_payload(decision: dict) -> dict:
    """Return the immutable semantic DecisionBundle surface used for replay proof.

    Runtime execution metadata such as ``workflow_run_id`` is intentionally excluded:
    it identifies the execution that produced an otherwise identical sealed decision,
    not the recommendation itself. Recommendation, certification, optimiser result,
    serving policy, contingency state, evidence interpretation, and serving health are
    all retained and therefore must reproduce exactly.
    """
    diagnostics = decision.get("provider_diagnostics")
    if not isinstance(diagnostics, dict):
        raise RuntimeError("DecisionBundle provider diagnostics are missing or invalid")
    return {
        "schema_version": decision.get("schema_version"),
        "system_decision": decision.get("system_decision"),
        "certification": decision.get("certification"),
        "provider_diagnostics": {
            "max_contiguous_horizon": diagnostics.get("max_contiguous_horizon"),
            "contingency_qualified_horizon": diagnostics.get(
                "contingency_qualified_horizon"
            ),
            "contingency_missing_by_horizon": diagnostics.get(
                "contingency_missing_by_horizon"
            ),
            "serving_provider_by_horizon": diagnostics.get(
                "serving_provider_by_horizon"
            ),
            "decision_optimisation": diagnostics.get("decision_optimisation"),
            "runtime_serving_h1_health": diagnostics.get(
                "runtime_serving_h1_health"
            ),
        },
        "evidence_manifest": decision.get("evidence_manifest"),
    }


# Backward-compatible private name for focused tests/evaluator code that already used
# the pre-hardening helper. New code should use the public semantic contract above.
_replay_security_payload = replay_security_payload


def _assert_decision_matches_frozen_replay(snapshot, decision: dict) -> None:
    """Fail closed unless an offline re-solve reproduces the published decision."""
    with tempfile.TemporaryDirectory(prefix="apex-v2-publication-replay-") as tmp:
        replay_bundle = solve_snapshot(
            snapshot.root,
            Path(tmp) / "decision_bundle.json",
        )
    expected = replay_security_payload(dataclass_to_dict(replay_bundle))
    observed = replay_security_payload(decision)
    if _impl.canonical_json_bytes(observed) != _impl.canonical_json_bytes(expected):
        raise RuntimeError(
            "DecisionBundle recommendation/certification does not match "
            "deterministic replay of the frozen snapshot"
        )


def build_publication_materials(
    snapshot_path: Path,
    decision_path: Path,
    output_dir: Path,
):
    """Verify sealed-input replay before delegating to artifact construction."""
    snapshot = open_frozen_snapshot(snapshot_path)
    decision = json.loads(Path(decision_path).read_text(encoding="utf-8"))
    run = snapshot.read_json("run.json")
    _impl._assert_decision_bound_to_snapshot(snapshot, decision, run)
    _assert_decision_matches_frozen_replay(snapshot, decision)
    return _impl.build_publication_materials(
        snapshot_path,
        decision_path,
        output_dir,
    )
