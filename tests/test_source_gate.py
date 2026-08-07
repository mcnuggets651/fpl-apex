from apex_fpl.services.provenance import SourceStatus
from apex_fpl.services.source_gate import evaluate_source_gate


def test_strict_gate_requires_real_airsenal():
    sources = [
        SourceStatus("official_fpl", True, "ok"),
        SourceStatus("fpl_core_playerstats", True, "ok"),
        SourceStatus("airsenal", True, "optional projection export not configured"),
    ]
    gate = evaluate_source_gate(sources, 0, require_airsenal=True)
    assert gate.safe_to_act is False
    assert any("AIrsenal" in b for b in gate.blockers)


def test_gate_passes_with_core_and_airsenal():
    sources = [
        SourceStatus("official_fpl", True, "ok"),
        SourceStatus("fpl_core_playerstats", True, "ok"),
        SourceStatus("airsenal", True, "3000 projection rows"),
    ]
    gate = evaluate_source_gate(sources, 0, require_airsenal=True)
    assert gate.safe_to_act is True
