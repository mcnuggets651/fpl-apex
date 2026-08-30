from apex.runtime.tournament_standings import (
    build_tournament_standings,
    canonical_evaluations,
)


def _payload(
    *,
    gameweek,
    run_id,
    frozen_at,
    actionable=True,
    airsenal_error=20.0,
    dastan_error=18.0,
):
    return {
        "schema_version": 2,
        "season": "2026-2027",
        "gameweek": gameweek,
        "run_id": run_id,
        "frozen_at": frozen_at,
        "valid_until": f"2026-09-{gameweek + 2:02d}T17:30:00+00:00",
        "certification_actionable": actionable,
        "champion_provider_id": "airsenal",
        "providers": {
            "airsenal": {
                "decision_surface": {"rows": 20, "mae": airsenal_error / 20},
                "decision_surface_forecast_rows": 20,
                "decision_surface_required_rows": 20,
            },
            "dastan": {
                "decision_surface": {"rows": 20, "mae": dastan_error / 20},
                "decision_surface_forecast_rows": 20,
                "decision_surface_required_rows": 20,
            },
        },
        "all_pairwise": {
            "airsenal::dastan": {
                "provider_a": "airsenal",
                "provider_b": "dastan",
                "paired_rows": 20,
                "provider_a_absolute_error_sum": airsenal_error,
                "provider_b_absolute_error_sum": dastan_error,
            }
        },
        "supported_horizons_by_provider": {
            "airsenal": [1, 2, 3, 4, 5, 6, 7, 8],
            "dastan": [1],
        },
    }


def test_canonical_evaluations_keeps_latest_actionable_predeadline_attempt_per_gw():
    older = _payload(
        gameweek=3,
        run_id="old",
        frozen_at="2026-09-04T10:00:00+00:00",
    )
    newer = _payload(
        gameweek=3,
        run_id="new",
        frozen_at="2026-09-04T12:00:00+00:00",
    )
    blocked = _payload(
        gameweek=3,
        run_id="blocked",
        frozen_at="2026-09-04T13:00:00+00:00",
        actionable=False,
    )
    result = canonical_evaluations([older, newer, blocked])
    assert [row["run_id"] for row in result] == ["new"]


def test_standings_aggregate_pairwise_errors_without_promoting_h1_only_model():
    payloads = [
        _payload(
            gameweek=gw,
            run_id=f"gw{gw}",
            frozen_at=f"2026-09-{gw:02d}T10:00:00+00:00",
            airsenal_error=40.0,
            dastan_error=30.0,
        )
        for gw in range(1, 9)
    ]
    result = build_tournament_standings(payloads)
    challenger = result["challengers"]["dastan"]

    assert result["champion_provider_id"] == "airsenal"
    assert len(result["completed_gameweeks"]) == 8
    assert challenger["expanding_pair"]["paired_rows"] == 160
    assert challenger["expanding_pair"]["provider_a_mae"] == 2.0
    assert challenger["expanding_pair"]["provider_b_mae"] == 1.5
    assert challenger["horizon_compatible"] is False
    assert challenger["promotion"]["eligible"] is False
    assert "challenger does not support the production decision horizon" in challenger["promotion"]["reasons"]
    assert challenger["decision_quality_status"] == "NOT_YET_MEASURED"
