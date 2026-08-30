from __future__ import annotations

from apex.domain.models import (
    ProductionProjectionSurface,
    ProjectionRow,
    ReasonCode,
)
from apex.governance.certification import certify
from apex.runtime.solve import _contingency_qualified_horizon


def _surface(rows) -> ProductionProjectionSurface:
    return ProductionProjectionSurface(
        1,
        "airsenal",
        "pinned",
        "2026-08-29T12:00:00Z",
        "2026-2027",
        "official",
        "fpl-2026-27-v1",
        (1, 2),
        tuple(rows),
    )


def test_certification_blocks_missing_contingency_model() -> None:
    result = certify(
        official=None,
        serving=None,
        decision=None,
        contingency_model_complete=False,
    )
    assert result.actionable is False
    assert ReasonCode.CONTINGENCY_MODEL_INCOMPLETE in result.reasons


def test_contingency_horizon_stops_at_first_incomplete_horizon() -> None:
    rows = []
    for player_id in (1, 2, 3):
        rows.append(
            ProjectionRow(
                player_id,
                3,
                1,
                3.0,
                p_appearance=0.9,
            )
        )
        rows.append(
            ProjectionRow(
                player_id,
                4,
                2,
                3.0,
                p_appearance=None if player_id == 2 else 0.9,
            )
        )
    horizon, missing = _contingency_qualified_horizon(
        _surface(rows),
        frozenset({1, 2, 3}),
        2,
    )
    assert horizon == 1
    assert missing == {2: [2]}


def test_zero_appearance_with_nonzero_xp_is_not_coherent() -> None:
    rows = [
        ProjectionRow(1, 3, 1, 4.0, p_appearance=0.0),
        ProjectionRow(2, 3, 1, 0.0, p_appearance=0.0),
    ]
    horizon, missing = _contingency_qualified_horizon(
        ProductionProjectionSurface(
            1,
            "airsenal",
            "pinned",
            "2026-08-29T12:00:00Z",
            "2026-2027",
            "official",
            "fpl-2026-27-v1",
            (1,),
            tuple(rows),
        ),
        frozenset({1, 2}),
        1,
    )
    assert horizon == 0
    assert missing == {1: [1]}
