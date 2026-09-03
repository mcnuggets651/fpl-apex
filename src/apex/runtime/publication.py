from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from apex.domain.models import ProviderHealth, dataclass_to_dict
from apex.runtime.serde import official_from_dict, team_from_dict
from apex.runtime.serving import reconstruct_frozen_serving
from apex.runtime.snapshot import open_frozen_snapshot
from apex.runtime.solve import _runtime_freshness, solve_snapshot

from . import publication_impl as _impl

# Preserve the established publication module API, including private helpers used by
# evaluator/reveal code and focused contract tests. Only the final build boundary is
# replaced by the replay-verifying facade below.
for _name in dir(_impl):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_impl, _name)


# The authority-aware private query bridge needs the governing production identity,
# not merely the commit/config-file identity. The current production core split the
# publication implementation behind this facade after the original production-core
# identity fix was written, so adapt the established implementation at this boundary
# rather than replacing newer publication/replay hardening with the older module.
_original_public_identity = _impl._public_identity


def _public_identity(snapshot, decision: dict, run: dict, canonical: dict) -> dict:
    identity = _original_public_identity(snapshot, decision, run, canonical)
    identity["production_core_sha"] = run["production_core_sha"]
    return identity


_impl._public_identity = _public_identity


# Solver backend telemetry is useful diagnostics, but it is not part of the FPL
# decision identity. HiGHS/SciPy may emit different status text or a numerically tiny
# MIP-gap value on different CPU/runner images even when the integral incumbent,
# optimiser policy and exact FPL decision are identical. Replay must fail closed on
# decision-driving state, not on backend presentation/noise.
_NON_SEMANTIC_SOLVER_FIELDS = frozenset(
    {
        "message",
        "mip_gap",
        "primary_message",
        "secondary_message",
        "next_candidate_message",
    }
)


def _semantic_decision_optimisation(value):
    if not isinstance(value, dict):
        return value
    semantic = dict(value)
    solver = semantic.get("solver")
    if isinstance(solver, dict):
        semantic["solver"] = {
            key: item
            for key, item in solver.items()
            if key not in _NON_SEMANTIC_SOLVER_FIELDS
        }
    return semantic


def replay_security_payload(decision: dict) -> dict:
    """Return the immutable semantic DecisionBundle surface used for replay proof.

    Runtime execution metadata such as ``workflow_run_id`` is intentionally excluded:
    it identifies the execution that produced an otherwise identical sealed decision,
    not the recommendation itself. Backend-only solver telemetry is also excluded when
    it cannot change the optimiser policy or FPL action. Recommendation,
    certification, decision-driving optimiser state, serving policy, contingency
    state, evidence interpretation, and serving health are all retained and therefore
    must reproduce exactly.
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
            "decision_optimisation": _semantic_decision_optimisation(
                diagnostics.get("decision_optimisation")
            ),
            "runtime_serving_h1_health": diagnostics.get(
                "runtime_serving_h1_health"
            ),
        },
        "evidence_manifest": decision.get("evidence_manifest"),
    }


# Backward-compatible private name for focused tests/evaluator code that already used
# the pre-hardening helper. New code should use the public semantic contract above.
_replay_security_payload = replay_security_payload


def _replay_mismatch_paths(observed, expected, path: str = "$") -> list[str]:
    """Return value-free JSON paths that differ across a replay comparison.

    Decision payloads can contain owner-private FPL material.  A production failure
    therefore reports only structural paths, never either value, while still making
    the remaining nondeterminism diagnosable from sanitized Actions logs.
    """
    if type(observed) is not type(expected):
        return [path]
    if isinstance(observed, dict):
        mismatches = []
        for key in sorted(set(observed) | set(expected)):
            child = f"{path}.{key}"
            if key not in observed or key not in expected:
                mismatches.append(child)
            else:
                mismatches.extend(
                    _replay_mismatch_paths(observed[key], expected[key], child)
                )
        return mismatches
    if isinstance(observed, list):
        mismatches = []
        if len(observed) != len(expected):
            mismatches.append(f"{path}.length")
        for index, (observed_item, expected_item) in enumerate(
            zip(observed, expected, strict=False)
        ):
            mismatches.extend(
                _replay_mismatch_paths(
                    observed_item,
                    expected_item,
                    f"{path}[{index}]",
                )
            )
        return mismatches
    return [] if observed == expected else [path]


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
        mismatch_paths = _replay_mismatch_paths(observed, expected)
        diagnostic = ", ".join(mismatch_paths[:20])
        if len(mismatch_paths) > 20:
            diagnostic += f", ... (+{len(mismatch_paths) - 20} more)"
        raise RuntimeError(
            "DecisionBundle recommendation/certification does not match "
            "deterministic replay of the frozen snapshot; "
            f"value-free mismatch paths: {diagnostic or '$'}"
        )


def _publication_utc_now(now: datetime | None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _parse_deadline(value) -> datetime:
    try:
        deadline = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("publication refused: frozen deadline is invalid") from exc
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return deadline.astimezone(timezone.utc)


def assert_publication_safe_now(
    snapshot_path: Path,
    decision_path: Path,
    *,
    now: datetime | None = None,
) -> None:
    """Fail closed if an actionable sealed decision is no longer safe to release.

    Replay is evaluated at the immutable snapshot clock so it can prove determinism.
    Release safety is a different question and is evaluated against real wall clock:
    an actionable decision may not escape after its FPL deadline or after the serving
    champion has crossed the freshness SLA sealed into the snapshot.
    """
    snapshot = open_frozen_snapshot(snapshot_path)
    decision = json.loads(Path(decision_path).read_text(encoding="utf-8"))
    certification = decision.get("certification")
    if not isinstance(certification, dict):
        raise RuntimeError("publication refused: DecisionBundle certification is invalid")
    if certification.get("actionable") is not True:
        return

    current = _publication_utc_now(now)
    run = snapshot.read_json("run.json")
    if current >= _parse_deadline(run.get("deadline")):
        raise RuntimeError("publication refused: actionable decision deadline has passed")

    official = official_from_dict(snapshot.read_json("official.json"))
    team_raw = snapshot.read_json("team_state.json")
    team = team_from_dict(team_raw) if team_raw else None
    matrix = snapshot.read_json("qualification_matrix.json")
    _, _, policy, _, _ = reconstruct_frozen_serving(
        snapshot, official, team, run, matrix
    )
    serving_h1 = _runtime_freshness(policy.get(1), snapshot, current)
    if serving_h1 is None:
        raise RuntimeError("publication refused: serving champion is unavailable")
    if serving_h1.health == ProviderHealth.STALE:
        raise RuntimeError("publication refused: serving champion is stale")
    if serving_h1.health in {ProviderHealth.INCOMPLETE, ProviderHealth.ERROR}:
        raise RuntimeError("publication refused: serving champion is incomplete")


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
