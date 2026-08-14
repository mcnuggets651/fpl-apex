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
    "src/apex_fpl/services/projection_audit.py",
    '''    for label, col in EXPERT_CONTRIBUTIONS.items():\n        d[f"canonical_{label}_contribution"] = _numeric(d, col) * d["horizon_discount"]\n    d["canonical_xp_discounted"] = _numeric(d, "xp") * d["horizon_discount"]\n''',
    '''    for label, col in EXPERT_CONTRIBUTIONS.items():\n        raw = _numeric(d, col)\n        d[f"raw_{label}_contribution"] = raw\n        d[f"discounted_{label}_contribution"] = raw * d["horizon_discount"]\n    d["raw_canonical_xp"] = _numeric(d, "xp")\n    d["discounted_horizon_utility_component"] = (\n        d["raw_canonical_xp"] * d["horizon_discount"]\n    )\n''',
)

replace_once(
    "src/apex_fpl/services/projection_audit.py",
    '''    aggregations: dict[str, tuple[str, str]] = {\n        "horizon_canonical_xp": ("canonical_xp_discounted", "sum"),\n        "horizon_official_contribution": ("canonical_official_contribution", "sum"),\n        "horizon_apex_contribution": ("canonical_apex_contribution", "sum"),\n        "horizon_airsenal_contribution": ("canonical_airsenal_contribution", "sum"),\n        "horizon_market_contribution": ("canonical_market_contribution", "sum"),\n    }\n''',
    '''    aggregations: dict[str, tuple[str, str]] = {\n        "raw_horizon_canonical_xp": ("raw_canonical_xp", "sum"),\n        "discounted_horizon_utility": ("discounted_horizon_utility_component", "sum"),\n        "raw_horizon_official_contribution": ("raw_official_contribution", "sum"),\n        "raw_horizon_apex_contribution": ("raw_apex_contribution", "sum"),\n        "raw_horizon_airsenal_contribution": ("raw_airsenal_contribution", "sum"),\n        "raw_horizon_market_contribution": ("raw_market_contribution", "sum"),\n        "discounted_horizon_official_contribution": ("discounted_official_contribution", "sum"),\n        "discounted_horizon_apex_contribution": ("discounted_apex_contribution", "sum"),\n        "discounted_horizon_airsenal_contribution": ("discounted_airsenal_contribution", "sum"),\n        "discounted_horizon_market_contribution": ("discounted_market_contribution", "sum"),\n    }\n''',
)

replace_once(
    "src/apex_fpl/services/projection_audit.py",
    '''    return out.sort_values("horizon_canonical_xp", ascending=False).reset_index(drop=True)\n''',
    '''    return out.sort_values("raw_horizon_canonical_xp", ascending=False).reset_index(drop=True)\n''',
)

replace_once(
    "src/apex_fpl/services/pipeline.py",
    '''        "preseason_xg90",\n        "preseason_xa90",\n        "gw1_xp",\n''',
    '''        "preseason_xg90",\n        "preseason_xa90",\n        "preseason_goals90",\n        "preseason_assists90",\n        "preseason_shots90",\n        "preseason_shots_on_target90",\n        "preseason_chances_created90",\n        "preseason_box_touches90",\n        "preseason_xg_observed",\n        "preseason_xa_observed",\n        "preseason_goals_observed",\n        "preseason_assists_observed",\n        "preseason_shots_observed",\n        "gw1_xp",\n''',
)

Path("tests/test_projection_audit_horizon_semantics.py").write_text(
    '''from __future__ import annotations\n\nimport pandas as pd\nimport pytest\n\nfrom apex_fpl.services.projection_audit import build_projection_decomposition\n\n\ndef test_projection_audit_separates_raw_xp_from_discounted_utility():\n    rows = []\n    for gw in (1, 2):\n        row = {\n            "player_id": 1,\n            "gw": gw,\n            "xp": 10.0,\n            "apex_xp": 10.0,\n            "xp_expert_official_ep": 2.0,\n            "xp_expert_apex_model": 5.0,\n            "xp_expert_airsenal": 3.0,\n            "xp_expert_market": 0.0,\n        }\n        for col in (\n            "xp_appearance",\n            "xp_attack",\n            "xp_clean_sheet",\n            "xp_defensive_contribution",\n            "xp_saves",\n            "xp_bonus_prior",\n            "xp_set_piece_prior",\n        ):\n            row[col] = 10.0 / 7.0\n        rows.append(row)\n    out = build_projection_decomposition(pd.DataFrame(rows), [1, 2], decay=0.90).iloc[0]\n    assert out["raw_horizon_canonical_xp"] == pytest.approx(20.0)\n    assert out["discounted_horizon_utility"] == pytest.approx(19.0)\n    assert out["raw_horizon_official_contribution"] == pytest.approx(4.0)\n    assert out["discounted_horizon_official_contribution"] == pytest.approx(3.8)\n''',
    encoding="utf-8",
)
