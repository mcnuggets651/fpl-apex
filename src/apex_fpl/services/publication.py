from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def invalidate_published_decision(
    output_dir: Path,
    *,
    reason: str,
    source_name: str,
    now: datetime | None = None,
) -> None:
    """Atomically make a previously published decision non-actionable.

    Required-source refresh workflows call this before committing their new input
    to ``main``. That guarantees a newer required input can never coexist with an
    older ``safe_to_act=true`` packet while the next Unified rebuild is queued.
    """
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    blocker = f"required source changed after canonical build: {source_name}: {reason}"

    recommendation_path = output_dir / "apex_recommendation_latest.json"
    context_path = output_dir / "apex_answer_context.json"
    markdown_path = output_dir / "apex_recommendation_latest.md"

    recommendation = _read_json(recommendation_path)
    recommendation["ready_to_act"] = False
    recommendation["recommendation"] = None
    recommendation["strategy_stage"] = "invalidated_pending_rebuild"
    recommendation["invalidated_at"] = stamp
    recommendation["invalidated_source"] = source_name
    recommendation["blockers"] = list(
        dict.fromkeys([*(recommendation.get("blockers") or []), blocker])
    )
    recommendation_path.parent.mkdir(parents=True, exist_ok=True)
    recommendation_path.write_text(
        json.dumps(recommendation, indent=2) + "\n", encoding="utf-8"
    )

    context = _read_json(context_path)
    context["safe_to_act"] = False
    context["recommendation"] = None
    context["production_result"] = None
    context["invalidated_at"] = stamp
    context["invalidated_source"] = source_name
    context["blockers"] = list(
        dict.fromkeys([*(context.get("blockers") or []), blocker])
    )
    context_path.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")

    markdown_path.write_text(
        "# Apex Unified Recommendation — NOT READY\n\n"
        f"- {blocker}\n"
        f"- Invalidated at: {stamp}\n"
        "- A fresh Apex Unified rebuild is required before acting.\n",
        encoding="utf-8",
    )
