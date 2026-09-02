from pathlib import Path

import pytest

from apex.sources.evidence import load_evidence_sources


def test_evidence_source_rejects_string_required_boolean(tmp_path: Path):
    path = tmp_path / "sources.yaml"
    path.write_text(
        """feeds:
  - name: Official
    url: https://example.com/official
    tier: official_club
    required: "false"
""",
        encoding="utf-8",
    )
    with pytest.raises((RuntimeError, ValueError), match="required|boolean"):
        load_evidence_sources(path)
