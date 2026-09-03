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


def test_emit_corrected_initial_squad_replay_probe(tmp_path):
    snapshot = _freeze(tmp_path / "probe-snapshots", "golden-initial", 1, None)
    bundle = solve_snapshot(snapshot.root, tmp_path / "probe.json", now=REPLAY_NOW)
    semantic = replay_security_payload(dataclass_to_dict(bundle))
    probe = {
        "semantic_digest": _digest(semantic),
        "system_decision": semantic["system_decision"],
        "decision_optimisation": semantic["provider_diagnostics"]["decision_optimisation"],
    }
    raise AssertionError("PRIMARY_LOCK_REPLAY_PROBE=" + json.dumps(probe, sort_keys=True))
