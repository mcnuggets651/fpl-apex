from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXACT_REF = "ref: ${{ github.event.pull_request.head.sha || github.sha }}"


def _assert_every_checkout_is_exact(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    checkout_count = text.count("uses: actions/checkout@")
    exact_ref_count = text.count(EXACT_REF)
    assert checkout_count > 0
    assert exact_ref_count == checkout_count


def test_apex_ci_certifies_the_exact_declared_source_sha() -> None:
    _assert_every_checkout_is_exact(ROOT / ".github/workflows/apex.yml")


def test_v2_shadow_certifies_the_exact_declared_source_sha() -> None:
    _assert_every_checkout_is_exact(ROOT / ".github/workflows/v2-shadow-production.yml")
