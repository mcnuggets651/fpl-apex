from pathlib import Path


def test_production_runtime_does_not_serialize_internal_transfer_candidates() -> None:
    source = Path("src/apex/runtime/solve.py").read_text(encoding="utf-8")

    # Candidate routes contain exact manager squad/player IDs. Production may
    # consume them in-memory in a future certified successor, but the existing
    # diagnostics/publication path must never serialize the whole optimisation
    # result or the internal candidate-route collection.
    assert "transfer_result.candidate_routes" not in source
    assert "dataclass_to_dict(transfer_result)" not in source
