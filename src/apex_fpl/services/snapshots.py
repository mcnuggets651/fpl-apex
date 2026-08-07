from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from apex_fpl.data.official import OfficialSnapshot


def write_official_snapshot(snapshot: OfficialSnapshot, root: Path) -> dict:
    """Persist an immutable, auditable official snapshot and checksum manifest."""
    root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}-{uuid4().hex[:8]}"
    target = root / run_id
    target.mkdir(parents=True, exist_ok=False)
    bootstrap = snapshot.raw_bootstrap
    fixtures = snapshot.raw_fixtures if snapshot.raw_fixtures is not None else snapshot.fixtures.to_dict("records")
    (target / "bootstrap-static.json").write_text(json.dumps(bootstrap, ensure_ascii=False, separators=(",", ":")))
    (target / "fixtures.json").write_text(json.dumps(fixtures, ensure_ascii=False, separators=(",", ":")))
    manifest = {
        "snapshot_id": run_id,
        "retrieved_at": snapshot.retrieved_at or now.isoformat(),
        "players": int(len(snapshot.players)),
        "fixtures": int(len(snapshot.fixtures)),
        "bootstrap_sha256": snapshot.bootstrap_sha256,
        "fixtures_sha256": snapshot.fixtures_sha256,
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2))
    latest = root / "latest.json"
    latest.write_text(json.dumps(manifest, indent=2))
    return manifest
