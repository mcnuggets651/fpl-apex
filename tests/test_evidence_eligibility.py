from types import SimpleNamespace

import pandas as pd

from apex_fpl.services.decision_eligibility import (
    captain_eligible_ids,
    evidence_eligibility,
    source_health_status,
)


def _players():
    return pd.DataFrame(
        [
            {"player_id": 1, "minutes_confidence": 0.9, "role_confidence": 0.8,
             "expected_minutes": 80, "start_probability": 0.9,
             "appearance_probability": 0.95, "projection_confidence": 0.8},
            {"player_id": 2, "minutes_confidence": 0.5, "role_confidence": 0.5,
             "expected_minutes": 45, "start_probability": 0.45,
             "appearance_probability": 0.65, "projection_confidence": 0.35},
        ]
    )


def test_quantitative_uncertainty_is_diagnostic_not_an_xi_exclusion():
    players, report = evidence_eligibility(_players(), pd.DataFrame())
    indexed = players.set_index("player_id")
    assert bool(indexed.loc[1, "xi_evidence_eligible"]) is True
    assert bool(indexed.loc[2, "xi_evidence_eligible"]) is True
    assert report["xi_ineligible_ids"] == []
    assert report["uncertainty_diagnostic_ids"] == [2]
    assert indexed.loc[2, "evidence_state"] == "uncertain_unverified"


def test_uncertain_player_can_be_captain_when_ev_and_fallback_mechanics_support_it():
    players, _ = evidence_eligibility(_players(), pd.DataFrame())
    assert captain_eligible_ids(players) == {1, 2}


def test_syndicated_copy_is_one_event_not_independent_corroboration():
    news = pd.DataFrame(
        [
            {"player_id": 2, "headline": "Two will start", "summary": "",
             "source_name": "A", "source_tier": "trusted_media",
             "eligible_for_projection": True, "multiplier": 1.0,
             "minutes_delta": 8.0, "start_probability_delta": 0.1},
            {"player_id": 2, "headline": "Two will start", "summary": "",
             "source_name": "B", "source_tier": "trusted_media",
             "eligible_for_projection": True, "multiplier": 1.0,
             "minutes_delta": 8.0, "start_probability_delta": 0.1},
        ]
    )
    players, report = evidence_eligibility(_players(), news)
    assert bool(players.set_index("player_id").loc[2, "xi_evidence_eligible"]) is True
    assert report["uncertainty_diagnostic_ids"] == [2]


def test_source_health_threshold_is_numeric_and_sealed():
    status = SimpleNamespace(
        name="news_source_health",
        version='{"configured_sources":3,"healthy_sources":2,"fresh_timestamped_items":1}',
    )
    assert source_health_status([status])["ready"] is True
    status.version = '{"configured_sources":3,"healthy_sources":1,"fresh_timestamped_items":9}'
    assert source_health_status([status])["ready"] is False


def test_single_trusted_negative_is_visible_but_not_an_exclusion_ceiling():
    news = pd.DataFrame(
        [{"player_id": 1, "headline": "One injury doubt", "summary": "",
          "source_name": "A", "source_tier": "trusted_media",
          "evidence_type": "availability", "eligible_for_projection": True,
          "multiplier": 0.65, "minutes_delta": 0.0,
          "start_probability_delta": 0.0}]
    )
    players, _ = evidence_eligibility(_players(), news)
    assert bool(players.set_index("player_id").loc[1, "xi_evidence_eligible"]) is True


def test_official_adverse_status_is_an_absolute_xi_and_captain_ceiling():
    players = _players()
    players.loc[players.player_id.eq(1), "status"] = "i"
    eligible, report = evidence_eligibility(players, pd.DataFrame())
    indexed = eligible.set_index("player_id")
    assert bool(indexed.loc[1, "xi_evidence_eligible"]) is False
    assert bool(indexed.loc[1, "captain_evidence_eligible"]) is False
    assert report["reasons"]["1"] == ["official FPL adverse status/chance ceiling"]
    assert 1 not in captain_eligible_ids(eligible)


def test_two_independent_negative_reports_can_still_exclude():
    news = pd.DataFrame(
        [
            {"player_id": 1, "headline": "One likely out", "summary": "source A",
             "source_name": "A", "source_tier": "trusted_media",
             "evidence_type": "availability", "eligible_for_projection": True,
             "multiplier": 0.4, "minutes_delta": 0.0,
             "start_probability_delta": 0.0},
            {"player_id": 1, "headline": "One misses training", "summary": "source B",
             "source_name": "B", "source_tier": "trusted_media",
             "evidence_type": "availability", "eligible_for_projection": True,
             "multiplier": 0.5, "minutes_delta": 0.0,
             "start_probability_delta": 0.0},
        ]
    )
    eligible, report = evidence_eligibility(_players(), news)
    assert bool(eligible.set_index("player_id").loc[1, "xi_evidence_eligible"]) is False
    assert report["reasons"]["1"] == ["current decision-grade negative evidence"]
