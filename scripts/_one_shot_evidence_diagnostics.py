from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one replacement target, found {count}")
    target.write_text(text.replace(old, new), encoding="utf-8")


replace_once(
    "src/apex_fpl/services/enrichment.py",
    '''    if matched < 1:\n        raise RuntimeError(\n            "Understat player production enrichment has zero usable mapped rows"\n        )\n    return enriched\n''',
    '''    if matched < 1:\n        raise RuntimeError(\n            "Understat player production enrichment has zero usable mapped rows"\n        )\n    enriched["understat_player_matched"] = (\n        pd.to_numeric(enriched["understat_xg90"], errors="coerce").notna()\n        & pd.to_numeric(enriched["understat_xa90"], errors="coerce").notna()\n    )\n    if "understat_match_method" not in enriched.columns:\n        enriched["understat_match_method"] = pd.NA\n    return enriched\n''',
)

replace_once(
    "src/apex_fpl/services/pipeline.py",
    '''        "preseason_shots_observed",\n        "gw1_xp",\n''',
    '''        "preseason_shots_observed",\n        "understat_player_matched",\n        "understat_match_method",\n        "gw1_xp",\n''',
)

replace_once(
    "src/apex_fpl/services/data_quality.py",
    '''    stat_cols = [\n        col\n        for col in ("xg", "xa", "defensive_contributions")\n        if col in friendlies.columns\n    ]\n    if not stat_cols:\n        return QualityCheck(\n            "preseason_evidence",\n            "warning",\n            False,\n            f"{len(friendlies)} player-match rows contain minutes but no return statistics",\n            0.0,\n            None,\n        )\n    observed = friendlies[stat_cols].apply(pd.to_numeric, errors="coerce").notna()\n    coverage = float(observed.any(axis=1).mean())\n    status = "pass" if coverage >= 0.80 else "warning"\n    return QualityCheck(\n        "preseason_evidence",\n        status,\n        False,\n        f"{len(friendlies)} player-match rows; return-stat observation coverage={coverage:.1%}",\n        coverage,\n        0.80,\n    )\n''',
    '''    advanced_cols = [\n        col\n        for col in ("xg", "xa", "defensive_contributions")\n        if col in friendlies.columns\n    ]\n    event_cols = [\n        col\n        for col in (\n            "goals",\n            "assists",\n            "total_shots",\n            "shots_on_target",\n            "chances_created",\n            "touches_opposition_box",\n        )\n        if col in friendlies.columns\n    ]\n    advanced_coverage = (\n        float(\n            friendlies[advanced_cols]\n            .apply(pd.to_numeric, errors="coerce")\n            .notna()\n            .any(axis=1)\n            .mean()\n        )\n        if advanced_cols\n        else 0.0\n    )\n    event_coverage = (\n        float(\n            friendlies[event_cols]\n            .apply(pd.to_numeric, errors="coerce")\n            .notna()\n            .any(axis=1)\n            .mean()\n        )\n        if event_cols\n        else 0.0\n    )\n    status = "pass" if advanced_coverage >= 0.80 else "warning"\n    return QualityCheck(\n        "preseason_evidence",\n        status,\n        False,\n        (\n            f"{len(friendlies)} player-match rows; advanced xG/xA/defcon observation "\n            f"coverage={advanced_coverage:.1%}; reliable goals/assists/shots/chances "\n            f"evidence coverage={event_coverage:.1%}; event evidence is preserved but "\n            "does not affect attacking xP until its fallback challenger is historically validated"\n        ),\n        advanced_coverage,\n        0.80,\n    )\n''',
)

replace_once(
    "src/apex_fpl/data/core_insights.py",
    '''                    "xg",\n                    "xa",\n                    "defensive_contributions",\n                    "start_min",\n''',
    '''                    "xg",\n                    "xa",\n                    "defensive_contributions",\n                    "goals",\n                    "assists",\n                    "total_shots",\n                    "shots_on_target",\n                    "chances_created",\n                    "touches_opposition_box",\n                    "start_min",\n''',
)

Path("tests/test_evidence_diagnostics.py").write_text(
    '''from __future__ import annotations\n\nimport pandas as pd\n\nfrom apex_fpl.services.data_quality import _preseason_check\nfrom apex_fpl.services.enrichment import _enrich_understat_player_rates\n\n\ndef test_preseason_quality_distinguishes_advanced_and_event_evidence():\n    friendlies = pd.DataFrame(\n        {\n            "player_id": [1, 2],\n            "match_id": [10, 10],\n            "minutes_played": [90, 45],\n            "xg": [None, None],\n            "xa": [None, None],\n            "defensive_contributions": [None, None],\n            "goals": [2, 0],\n            "assists": [0, 1],\n            "total_shots": [5, 1],\n        }\n    )\n    check = _preseason_check(friendlies)\n    assert check.status == "warning"\n    assert check.coverage == 0.0\n    assert "advanced xG/xA/defcon observation coverage=0.0%" in check.detail\n    assert "evidence coverage=100.0%" in check.detail\n    assert "does not affect attacking xP" in check.detail\n\n\ndef test_understat_enrichment_exposes_match_method(monkeypatch):\n    players = pd.DataFrame(\n        {\n            "player_id": [1],\n            "first_name": ["João Pedro Junqueira"],\n            "second_name": ["de Jesus"],\n            "web_name": ["João Pedro"],\n            "team_name": ["Chelsea"],\n            "expected_goals_per_90_core": [0.45],\n            "expected_assists_per_90_core": [0.15],\n        }\n    )\n    normalized = pd.DataFrame(\n        {\n            "player_name": ["Joao Pedro"],\n            "team_name": ["Chelsea"],\n            "understat_xg90": [0.5],\n            "understat_xa90": [0.2],\n        }\n    )\n    monkeypatch.setattr(\n        "apex_fpl.services.enrichment.fetch_understat_season",\n        lambda *args, **kwargs: {},\n    )\n    monkeypatch.setattr(\n        "apex_fpl.services.enrichment.normalise_understat_players",\n        lambda payload, year: normalized,\n    )\n    out = _enrich_understat_player_rates(players).iloc[0]\n    assert bool(out["understat_player_matched"]) is True\n    assert out["understat_match_method"] == "web_name_team"\n''',
    encoding="utf-8",
)
