from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from apex_fpl.services.decision_eligibility import evidence_eligibility


def _players() -> pd.DataFrame:
    return pd.DataFrame([
        {"player_id": 1, "web_name": "Alpha", "team": 1, "team_name": "Test", "position": "MID", "price": 5.0, "status": "a", "chance_of_playing_next_round": 100, "start_probability": 0.84, "expected_minutes": 76.0, "minutes_confidence": 0.9, "role_confidence": 0.9},
        {"player_id": 2, "web_name": "Beta", "team": 2, "team_name": "Other", "position": "MID", "price": 5.0, "status": "a", "chance_of_playing_next_round": 100, "start_probability": 0.80, "expected_minutes": 72.0, "minutes_confidence": 0.9, "role_confidence": 0.9},
    ])


def _news(rows: list[dict] | None = None) -> pd.DataFrame:
    columns = ["player_id", "eligible_for_projection", "source_tier", "source_name", "headline", "summary", "multiplier", "minutes_delta", "start_probability_delta", "evidence_type"]
    return pd.DataFrame(rows or [], columns=columns)


def _write_specialist(path: Path, votes: list[tuple[str, bool]], *, now: datetime, player_id: int = 1, player_name: str = "Alpha", expired: bool = False) -> None:
    expires = now - timedelta(minutes=1) if expired else now + timedelta(hours=4)
    rows = [{"player_id": player_id, "source_player_name": player_name, "source": source, "predicted_start": predicted_start, "source_url": "https://example.com/predicted-xi", "published_at": (now - timedelta(hours=1)).isoformat(), "retrieved_at": now.isoformat(), "expires_at": expires.isoformat()} for source, predicted_start in votes]
    pd.DataFrame(rows).to_csv(path, index=False)


def test_two_source_nonstart_consensus_constrains_before_solve(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    path = tmp_path / "specialist.csv"
    _write_specialist(path, [("fantasy_football_scout", False), ("onefpl", False)], now=now)
    eligible, report = evidence_eligibility(_players(), _news(), specialist_predictions_path=path, now=now)
    alpha = eligible.loc[eligible["player_id"].eq(1)].iloc[0]
    assert bool(alpha["xi_evidence_eligible"]) is False
    assert report["squad_ineligible_ids"] == []
    assert 1 in report["xi_ineligible_ids"]
    assert report["specialist_consensus"]["1"] == "bench"


def test_split_specialist_evidence_does_not_hard_ban(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    path = tmp_path / "specialist.csv"
    _write_specialist(path, [("fantasy_football_scout", False), ("onefpl", True)], now=now)
    eligible, report = evidence_eligibility(_players(), _news(), specialist_predictions_path=path, now=now)
    assert bool(eligible.loc[eligible["player_id"].eq(1), "xi_evidence_eligible"].iloc[0]) is True
    assert report["squad_ineligible_ids"] == []
    assert report["specialist_consensus"]["1"] == "split"


def test_authoritative_positive_evidence_outranks_specialist_nonstart(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    path = tmp_path / "specialist.csv"
    _write_specialist(path, [("fantasy_football_scout", False), ("onefpl", False)], now=now)
    news = _news([{"player_id": 1, "eligible_for_projection": True, "source_tier": "official_club", "source_name": "Test FC", "headline": "Manager confirms Alpha starts", "summary": "Alpha is available and expected to start.", "multiplier": 1.0, "minutes_delta": 5.0, "start_probability_delta": 0.1, "evidence_type": "manager"}])
    eligible, report = evidence_eligibility(_players(), news, specialist_predictions_path=path, now=now)
    assert bool(eligible.loc[eligible["player_id"].eq(1), "xi_evidence_eligible"].iloc[0]) is True
    assert report["squad_ineligible_ids"] == []


def test_wrong_id_name_pair_fails_closed(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    path = tmp_path / "specialist.csv"
    _write_specialist(path, [("fantasy_football_scout", False), ("onefpl", False)], now=now, player_name="Wrong Name")
    with pytest.raises(ValueError, match="identity failed"):
        evidence_eligibility(_players(), _news(), specialist_predictions_path=path, now=now)


def test_stale_specialist_evidence_cannot_create_hard_constraint(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    path = tmp_path / "specialist.csv"
    _write_specialist(path, [("fantasy_football_scout", False), ("onefpl", False)], now=now, expired=True)
    eligible, report = evidence_eligibility(_players(), _news(), specialist_predictions_path=path, now=now)
    assert bool(eligible.loc[eligible["player_id"].eq(1), "xi_evidence_eligible"].iloc[0]) is True
    assert report["xi_ineligible_ids"] == []


def test_constrained_player_leaves_alternative_xi_candidate(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    path = tmp_path / "specialist.csv"
    _write_specialist(path, [("fantasy_football_scout", False), ("onefpl", False)], now=now)
    eligible, report = evidence_eligibility(_players(), _news(), specialist_predictions_path=path, now=now)
    assert 1 in report["xi_ineligible_ids"]
    assert bool(eligible.loc[eligible["player_id"].eq(2), "xi_evidence_eligible"].iloc[0]) is True
