from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_core_refresh_invalidation_uses_project_import_path():
    workflow = (ROOT / ".github/workflows/refresh-core-pin.yml").read_text(
        encoding="utf-8"
    )

    assert (
        "PYTHONPATH=src python scripts/invalidate_published_decision.py"
        in workflow
    )
