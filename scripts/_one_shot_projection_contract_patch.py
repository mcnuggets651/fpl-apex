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
    "src/apex_fpl/services/pipeline.py",
    '''def _summarise_horizons(proj: pd.DataFrame, gws: list[int]) -> pd.DataFrame:\n    pids = proj[["player_id"]].drop_duplicates().copy()\n    for horizon in (1, 3, 5, 8):\n        chosen = gws[: min(horizon, len(gws))]\n        vals = (\n            proj[proj["gw"].isin(chosen)]\n            .groupby("player_id")["weighted_xp"]\n            .sum()\n        )\n        pids[f"xpts_{horizon}"] = pids["player_id"].map(vals).fillna(0)\n    conf = proj.groupby("player_id")["projection_confidence"].mean()\n    pids["projection_confidence"] = pids["player_id"].map(conf).fillna(0)\n    return pids\n''',
    '''def _raw_projection_column(proj: pd.DataFrame) -> str:\n    for column in ("canonical_ev_xp", "xp", "risk_adjusted_xp"):\n        if column in proj.columns:\n            return column\n    raise ValueError("projection surface has no canonical expected-points column")\n\n\ndef _summarise_horizons(proj: pd.DataFrame, gws: list[int]) -> pd.DataFrame:\n    """Expose xpts_N as undiscounted cumulative expected FPL points.\n\n    Fixture decay is a decision-policy utility transform, not a points forecast.\n    It must never be published under an xP label.\n    """\n    pids = proj[["player_id"]].drop_duplicates().copy()\n    raw_col = _raw_projection_column(proj)\n    for horizon in (1, 3, 5, 8):\n        chosen = gws[: min(horizon, len(gws))]\n        vals = (\n            proj[proj["gw"].isin(chosen)]\n            .groupby("player_id")[raw_col]\n            .sum()\n        )\n        pids[f"xpts_{horizon}"] = pids["player_id"].map(vals).fillna(0)\n    conf = proj.groupby("player_id")["projection_confidence"].mean()\n    pids["projection_confidence"] = pids["player_id"].map(conf).fillna(0)\n    return pids\n\n\ndef _horizon_totals(proj: pd.DataFrame) -> pd.DataFrame:\n    raw_col = _raw_projection_column(proj)\n    if "weighted_xp" not in proj.columns:\n        raise ValueError("projection surface has no discounted utility component")\n    out = proj.groupby("player_id", as_index=False).agg(\n        raw_horizon_xp=(raw_col, "sum"),\n        discounted_horizon_utility=("weighted_xp", "sum"),\n    )\n    # Compatibility alias: horizon_xp now has literal xP semantics. Any optimiser\n    # that wants discounted utility must use discounted_horizon_utility explicitly.\n    out["horizon_xp"] = out["raw_horizon_xp"]\n    return out\n''',
)

replace_once(
    "src/apex_fpl/services/pipeline.py",
    '''    proj = blend_projection(proj, settings.weights, settings.risk_penalty)\n    decay = {gw: settings.fixture_decay**i for i, gw in enumerate(gws)}\n    proj["decay"] = proj["gw"].map(decay)\n    proj["weighted_xp"] = proj["risk_adjusted_xp"] * proj["decay"]\n    summaries = _summarise_horizons(proj, gws)\n    horizon_vals = proj.groupby("player_id", as_index=False).agg(\n        horizon_xp=("weighted_xp", "sum")\n    )\n''',
    '''    proj = blend_projection(proj, settings.weights, settings.risk_penalty)\n    decay = {gw: settings.fixture_decay**i for i, gw in enumerate(gws)}\n    proj["decay"] = proj["gw"].map(decay)\n    proj["weighted_xp"] = proj["risk_adjusted_xp"] * proj["decay"]\n    proj["discounted_horizon_utility_component"] = proj["weighted_xp"]\n    summaries = _summarise_horizons(proj, gws)\n    horizon_vals = _horizon_totals(proj)\n''',
)

replace_once(
    "src/apex_fpl/services/pipeline.py",
    '''    for col in [\n        "horizon_xp",\n        "gw1_xp",\n''',
    '''    ranked["fixture_decay"] = float(settings.fixture_decay)\n    for col in [\n        "raw_horizon_xp",\n        "discounted_horizon_utility",\n        "horizon_xp",\n        "gw1_xp",\n''',
)

replace_once(
    "src/apex_fpl/services/pipeline.py",
    '''        "xpts_8",\n        "horizon_xp",\n        "projection_confidence",\n    ]\n''',
    '''        "xpts_8",\n        "raw_horizon_xp",\n        "discounted_horizon_utility",\n        "horizon_xp",\n        "fixture_decay",\n        "projection_confidence",\n    ]\n''',
)

replace_once(
    "src/apex_fpl/services/pipeline.py",
    '''    ].sort_values("horizon_xp", ascending=False)\n''',
    '''    ].sort_values("raw_horizon_xp", ascending=False)\n''',
)

replace_once(
    "src/apex_fpl/optimisation/squad.py",
    '''    horizon = pd.to_numeric(d["horizon_xp"], errors="coerce").fillna(0).to_numpy(float)\n    gw1 = pd.to_numeric(d.get("gw1_xp", d["horizon_xp"]), errors="coerce").fillna(0).to_numpy(float)\n''',
    '''    utility_col = (\n        "discounted_horizon_utility"\n        if "discounted_horizon_utility" in d.columns\n        else "horizon_xp"\n    )\n    horizon = pd.to_numeric(d[utility_col], errors="coerce").fillna(0).to_numpy(float)\n    gw1 = pd.to_numeric(d.get("gw1_xp", d["horizon_xp"]), errors="coerce").fillna(0).to_numpy(float)\n''',
)

replace_once(
    "src/apex_fpl/optimisation/squad.py",
    '''        "xpts_8",\n        "horizon_xp",\n        "projection_confidence",\n''',
    '''        "xpts_8",\n        "raw_horizon_xp",\n        "discounted_horizon_utility",\n        "horizon_xp",\n        "fixture_decay",\n        "projection_confidence",\n''',
)

replace_once(
    "src/apex_fpl/optimisation/initial_horizon.py",
    '''        "xpts_8",\n        "horizon_xp",\n        "projection_confidence",\n''',
    '''        "xpts_8",\n        "raw_horizon_xp",\n        "discounted_horizon_utility",\n        "horizon_xp",\n        "fixture_decay",\n        "projection_confidence",\n''',
)

replace_once(
    "scripts/build_canonical_recommendation.py",
    '''            "primary_selection": "maximum exact-mechanics expected points among the sealed near-optimal legal squad frontier",\n''',
    '''            "primary_selection": "maximum discounted exact-mechanics horizon utility among the sealed near-optimal legal squad frontier; raw cumulative xP is reported separately",\n''',
)

Path("tests/test_horizon_semantics.py").write_text(
    '''from __future__ import annotations\n\nimport pandas as pd\nimport pytest\n\nfrom apex_fpl.services.pipeline import _horizon_totals, _summarise_horizons\n\n\ndef _surface() -> pd.DataFrame:\n    return pd.DataFrame(\n        {\n            "player_id": [1, 1, 1],\n            "gw": [1, 2, 3],\n            "canonical_ev_xp": [10.0, 10.0, 10.0],\n            "risk_adjusted_xp": [10.0, 10.0, 10.0],\n            "weighted_xp": [10.0, 9.0, 8.1],\n            "projection_confidence": [0.8, 0.8, 0.8],\n        }\n    )\n\n\ndef test_xpts_are_raw_cumulative_expected_points_not_discounted_utility():\n    summary = _summarise_horizons(_surface(), [1, 2, 3]).iloc[0]\n    assert summary["xpts_1"] == pytest.approx(10.0)\n    assert summary["xpts_3"] == pytest.approx(30.0)\n    assert summary["xpts_3"] != pytest.approx(27.1)\n\n\ndef test_horizon_totals_expose_raw_xp_and_discounted_utility_separately():\n    totals = _horizon_totals(_surface()).iloc[0]\n    assert totals["raw_horizon_xp"] == pytest.approx(30.0)\n    assert totals["horizon_xp"] == pytest.approx(30.0)\n    assert totals["discounted_horizon_utility"] == pytest.approx(27.1)\n\n\ndef test_no_decay_makes_raw_xp_equal_utility():\n    surface = _surface()\n    surface["weighted_xp"] = surface["canonical_ev_xp"]\n    totals = _horizon_totals(surface).iloc[0]\n    assert totals["raw_horizon_xp"] == pytest.approx(totals["discounted_horizon_utility"])\n''',
    encoding="utf-8",
)
