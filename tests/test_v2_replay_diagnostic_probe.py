from __future__ import annotations

import hashlib
import json

from apex.domain.models import dataclass_to_dict
from apex.runtime.publication import replay_security_payload
from apex.runtime.publication_impl import canonical_json_bytes
from apex.runtime.solve import solve_snapshot
from test_v2_deterministic_replay import REPLAY_NOW, _freeze


def _digest(value) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def test_emit_initial_squad_semantic_replay_probe(tmp_path):
    snapshot = _freeze(tmp_path / "probe-snapshots", "golden-initial", 1, None)
    bundle = solve_snapshot(snapshot.root, tmp_path / "probe.json", now=REPLAY_NOW)
    semantic = replay_security_payload(dataclass_to_dict(bundle))
    probe = {
        "semantic_digest": _digest(semantic),
        "system_decision_digest": _digest(semantic["system_decision"]),
        "certification_digest": _digest(semantic["certification"]),
        "provider_diagnostics_digest": _digest(semantic["provider_diagnostics"]),
        "decision_optimisation_digest": _digest(
            semantic["provider_diagnostics"]["decision_optimisation"]
        ),
        "evidence_manifest_digest": _digest(semantic["evidence_manifest"]),
        "system_decision": semantic["system_decision"],
        "certification": semantic["certification"],
        "provider_diagnostics": semantic["provider_diagnostics"],
        "evidence_manifest": semantic["evidence_manifest"],
    }
    raise AssertionError("REPLAY_PROBE=" + json.dumps(probe, sort_keys=True))
