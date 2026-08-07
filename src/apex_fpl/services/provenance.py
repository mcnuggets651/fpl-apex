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
        if not self.checked_at:
            self.checked_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self):
        return asdict(self)


def load_upstream_pins(path: Path) -> dict:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    return payload.get("sources", {})
