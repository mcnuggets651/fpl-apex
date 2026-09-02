from pathlib import Path


FROZEN_SHA = "99cc7b51b0cff45462b567084cb1844cfe0a456f"


def test_decision_register_explicitly_supersedes_legacy_production_authority() -> None:
    text = Path("docs/APEX_DECISIONS.md").read_text(encoding="utf-8")
    marker = "## D031 — Apex V2 supersedes the V1/V1.5 production authority chain"
    assert marker in text
    current = text[text.index(marker) :]
    for needle in (
        FROZEN_SHA,
        "PR #90 must never be merged or advanced",
        ".github/workflows/apex-v2-daily-production.yml",
        "AIrsenal is the sole serving provider H1–H8",
        "production_influence = NONE",
        "serving_authorized = false",
        "docs/APEX_V2_AUTHORITY.json",
    ):
        assert needle in current
    assert "scripts/run_apex.py" in current
    assert "superseded" in current
