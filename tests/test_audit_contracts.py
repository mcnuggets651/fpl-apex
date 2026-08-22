from types import SimpleNamespace

import pandas as pd

from apex_fpl.services.audit_contracts import assess_diagnostic_surface


def _output(*, safety_blockers=()):
    return SimpleNamespace(
        players=pd.DataFrame(
            [
                {"player_id": 1, "web_name": "A"},
                {"player_id": 2, "web_name": "B"},
            ]
        ),
        projections=pd.DataFrame(
            [
                {"player_id": 1, "gw": 2, "xp": 4.0},
                {"player_id": 2, "gw": 2, "xp": 3.0},
            ]
        ),
        gameweeks=[2],
        integrity=pd.DataFrame(),
        safety=SimpleNamespace(
            safe_to_act=not safety_blockers,
            full_apex_ready=not safety_blockers,
            blockers=list(safety_blockers),
        ),
    )


def test_publication_blocker_does_not_masquerade_as_diagnostic_failure():
    output = _output(safety_blockers=("required source unhealthy: news_feeds",))

    readiness = assess_diagnostic_surface(output)

    assert readiness.ready is True
    assert readiness.blockers == ()
    assert readiness.publication_safe_to_act is False
    assert readiness.publication_blockers == (
        "required source unhealthy: news_feeds",
    )
    assert any("production publication is blocked" in row for row in readiness.warnings)


def test_duplicate_projection_key_blocks_diagnostic_surface():
    output = _output()
    output.projections = pd.concat(
        [output.projections, output.projections.iloc[[0]]], ignore_index=True
    )

    readiness = assess_diagnostic_surface(output)

    assert readiness.ready is False
    assert (
        "diagnostic projection surface has repeated player/Gameweek rows without "
        "fixture identity columns: is_home, opponent"
    ) in readiness.blockers


def test_non_finite_projection_blocks_diagnostic_surface():
    output = _output()
    output.projections.loc[0, "xp"] = float("nan")

    readiness = assess_diagnostic_surface(output)

    assert readiness.ready is False
    assert "diagnostic projection column xp contains non-finite values" in readiness.blockers


def test_missing_actionable_gameweek_blocks_diagnostic_surface():
    output = _output()
    output.gameweeks = []

    readiness = assess_diagnostic_surface(output)

    assert readiness.ready is False
    assert "diagnostic surface has no actionable gameweeks" in readiness.blockers
