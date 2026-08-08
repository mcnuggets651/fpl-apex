from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
from pathlib import Path


@dataclass
class SourceStatus:
    name: str
    ok: bool
    detail: str = ""
    checked_at: str = ""
    configured: bool = True
    version: str = ""

    def __post_init__(self):
        # Normalise bool-like values (notably numpy.bool_) at the provenance
        # boundary so readiness checks and JSON contracts always see native
        # Python booleans. Without this, json.dumps(..., default=str) can turn
        # a healthy np.bool_(True) into the string "True" and falsely block
        # strict `is True` production gates.
        self.ok = bool(self.ok)
        self.configured = bool(self.configured)
        if not self.checked_at:
            self.checked_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self):
        return asdict(self)


def load_upstream_pins(path: Path) -> dict:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    return payload.get("sources", {})
