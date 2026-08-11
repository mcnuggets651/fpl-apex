from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


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


def validate_core_pin(
    source: dict[str, Any],
    *,
    max_age_hours: float,
    now: datetime | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Validate and expose immutable FPL Core runtime provenance."""
    checked = now or datetime.now(timezone.utc)
    sha = str(source.get("commit") or "").strip()
    raw_time = str(source.get("committed_at") or "").strip()
    provenance: dict[str, Any] = {
        "commit": sha,
        "committed_at": raw_time,
        "checked_at": checked.isoformat(),
        "max_age_hours": float(max_age_hours),
        "newer_revision_available_at_resolution": source.get(
            "newer_revision_available"
        ),
        "resolved_at": source.get("resolved_at"),
    }
    if len(sha) != 40 or not raw_time:
        return False, "FPL Core pin lacks immutable SHA/commit timestamp", provenance
    try:
        committed = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        if committed.tzinfo is None:
            committed = committed.replace(tzinfo=timezone.utc)
    except ValueError:
        return False, "FPL Core pin has invalid commit timestamp", provenance
    age = (checked - committed).total_seconds() / 3600.0
    provenance["age_hours"] = max(age, 0.0)
    if age < -0.5:
        return False, f"FPL Core pin timestamp is {abs(age):.1f}h in the future", provenance
    if age > max_age_hours:
        return False, (
            f"FPL Core pin is stale ({age:.1f}h old; max {max_age_hours:.1f}h)"
        ), provenance
    return True, f"commit={sha[:12]}; age={max(age, 0):.1f}h", provenance
