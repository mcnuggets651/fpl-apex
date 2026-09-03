from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from apex.decision import optimiser as optimiser_module
from apex.decision.optimiser import optimise_initial_squad
from apex.domain.models import OfficialSnapshot
from test_v2_deterministic_replay import _players, _surface


def _fixture():
    official = OfficialSnapshot(
        1,
        "2026-2027",
        "2026-09-03T06:00:00Z",
        "lock-guard-official-hash",
        _players(),
        (),
        {2: "2026-09-12T10:00:00Z"},
    )
    return official, _surface(official, 1)


def _solver_result(vector, message):
    return SimpleNamespace(
        success=True,
        x=np.asarray(vector, dtype=float),
        message=message,
        mip_gap=0.0,
    )


def test_secondary_squad_stage_fails_closed_if_primary_lock_escapes(monkeypatch):
    official, surface = _fixture()
    count = len(official.players)
    first = np.zeros(3 * count)
    escaped = np.zeros(3 * count)
    escaped[count] = 1.0  # changes the primary XI objective by player 1 xP
    responses = iter(
        (
            _solver_result(first, "primary"),
            _solver_result(escaped, "secondary escaped"),
        )
    )
    monkeypatch.setattr(optimiser_module, "milp", lambda **_: next(responses))

    result = optimise_initial_squad(official, surface, candidate_limit=1)

    assert result.decision is None
    assert result.status == "ERROR"
    assert result.raw_solver["message"] == (
        "secondary squad-xP solve escaped primary optimum lock"
    )


def test_lexicographic_stage_fails_closed_if_squad_lock_escapes(monkeypatch):
    official, surface = _fixture()
    count = len(official.players)
    first = np.zeros(3 * count)
    secondary = np.zeros(3 * count)
    escaped = np.zeros(3 * count)
    escaped[0] = 1.0  # preserves zero primary xP but changes locked squad xP
    responses = iter(
        (
            _solver_result(first, "primary"),
            _solver_result(secondary, "secondary"),
            _solver_result(escaped, "lexicographic escaped"),
        )
    )
    monkeypatch.setattr(optimiser_module, "milp", lambda **_: next(responses))

    result = optimise_initial_squad(official, surface, candidate_limit=1)

    assert result.decision is None
    assert result.status == "ERROR"
    assert result.raw_solver["message"] == (
        "lexicographic tie-break escaped squad-xP optimum lock"
    )
