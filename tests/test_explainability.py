from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from apex_fpl.reporting.explain import (
    build_risk_report,
    component_summary,
    scenario_comparison,
)


def test_component_summary_identifies_top_xp_drivers():
    projections = pd.DataFrame(
        [
            {
                "player_id": 1,
                "xp_appearance": 1.8,
                "xp_attack": 3.5,
                "xp_clean_sheet": 0.4,
                "xp_defensive_contribution": 0.0,
                "xp_saves": 0.0,
                "xp_bonus_prior": 0.5,
                "xp_set_piece_prior": 0.3,
            },
            {
                "player_id": 1,
                "xp_appearance": 1.8,
                "xp_attack": 2.8,
                "xp_clean_sheet": 0.3,
                "xp_defensive_contribution": 0.0,
                "xp_saves": 0.0,
                "xp_bonus_prior": 0.4,
                "xp_set_piece_prior": 0.2,
            },
        ]
    )
    row = component_summary(projections).iloc[0]
    assert row["top_drivers"].startswith("attacking xG/xA")
    assert "minutes / appearance" in row["top_drivers"]


def test_risk_report_surfaces_minutes_confidence_and_news():
    players = pd.DataFrame(
        [
            {
                "player_id": 1,
                "web_name": "Risky",
                "team_name": "Team",
                "position": "MID",
                "price": 7.0,
                "status": "d",
                "expected_minutes": 52,
                "start_probability": 0.55,
                "projection_confidence": 0.42,
                "role_confidence": 0.50,
                "horizon_xp": 30,
            }
        ]
    )
    projections = pd.DataFrame(
        [{"player_id": 1, "expert_disagreement_sd": 1.8}]
    )
    news = pd.DataFrame(
        [
            {
                "player_id": 1,
                "multiplier": 0.65,
                "event_type": "availability",
                "headline": "Risky is a major doubt",
            }
        ]
    )
    risk = build_risk_report(players, projections, pd.DataFrame(), news).iloc[0]
    assert risk["risk_score"] > 0.5
    assert "expected minutes" in risk["risk_flags"]
    assert "projection models disagree" in risk["risk_flags"]
    assert "major doubt" in risk["risk_flags"]


def test_scenario_comparison_quantifies_haaland_structure_gap():
    squad_a = pd.DataFrame(
        [
            {
                "player_id": i,
                "price": 6.0,
                "horizon_xp": 30.0,
                "projection_confidence": 0.8,
            }
            for i in range(1, 16)
        ]
    )
    xi_a = squad_a.head(11).assign(gw1_xp=5.0)
    cap_a = xi_a.head(1)

    squad_b = squad_a.copy()
    squad_b["horizon_xp"] = 29.0
    xi_b = squad_b.head(11).assign(gw1_xp=4.8)
    cap_b = xi_b.head(1)

    empty = squad_a.iloc[0:0]
    scenarios = {
        "haaland": SimpleNamespace(
            status="Optimal",
            objective=100.0,
            squad=squad_a,
            xi=xi_a,
            captain=cap_a,
            vice_captain=empty,
            bench=empty,
        ),
        "no-haaland": SimpleNamespace(
            status="Optimal",
            objective=98.0,
            squad=squad_b,
            xi=xi_b,
            captain=cap_b,
            vice_captain=empty,
            bench=empty,
        ),
    }
    comparison = {row["scenario"]: row for row in scenario_comparison(scenarios)}
    assert comparison["haaland"]["horizon_gap_to_best"] == 0
    assert comparison["no-haaland"]["horizon_gap_to_best"] < 0
    assert comparison["haaland"]["gw1_total_with_captain"] > comparison["no-haaland"]["gw1_total_with_captain"]
