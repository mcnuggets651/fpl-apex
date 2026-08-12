import json
import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "run_pinnacle.py"
SPEC = importlib.util.spec_from_file_location("run_pinnacle", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
_write_blocked_payload = MODULE._write_blocked_payload


class _Bundle:
    created_at = "2026-08-12T09:14:00+00:00"
    bundle_id = "fresh-bundle"

    @staticmethod
    def lineage_summary():
        return {"contract": "apex-decision-bundle-v1", "bundle_id": "fresh-bundle"}


def test_blocked_pinnacle_writes_current_teamless_diagnostic(tmp_path: Path):
    blockers = ["official team strength is unavailable", "Core coverage is incomplete"]

    _write_blocked_payload(_Bundle(), blockers, tmp_path)

    payload = json.loads((tmp_path / "pinnacle_latest.json").read_text())
    assert payload["decision_bundle_id"] == "fresh-bundle"
    assert payload["pinnacle_ready"] is False
    assert payload["pinnacle_gate"]["blockers"] == blockers
    assert payload["safe_to_act"] is False
    assert payload["recommendation"] is None
    assert "squad" not in payload
