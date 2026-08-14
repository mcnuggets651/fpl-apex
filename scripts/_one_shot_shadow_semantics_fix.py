from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one target, found {count}")
    target.write_text(text.replace(old, new), encoding="utf-8")


replace_once(
    "src/apex_fpl/services/projection_audit.py",
    '''    for col in cols:\n        pcol, scol = f"production_{col}", f"shadow_{col}"\n        if pcol in d.columns and scol in d.columns:\n            d[f"discounted_production_{col}"] = _numeric(d, pcol) * d["discount"]\n            d[f"discounted_shadow_{col}"] = _numeric(d, scol) * d["discount"]\n\n    agg: dict[str, tuple[str, str]] = {}\n    for col in cols:\n        pcol, scol = f"discounted_production_{col}", f"discounted_shadow_{col}"\n        if pcol in d.columns and scol in d.columns:\n            agg[f"production_{col}"] = (pcol, "sum")\n            agg[f"shadow_{col}"] = (scol, "sum")\n    out = d.groupby("player_id", as_index=False).agg(**agg)\n    for col in cols:\n        pcol, scol = f"production_{col}", f"shadow_{col}"\n        if pcol in out.columns and scol in out.columns:\n            out[f"delta_{col}"] = out[scol] - out[pcol]\n    if "delta_apex_xp" in out.columns:\n        out = out.sort_values("delta_apex_xp", ascending=False)\n    return out.reset_index(drop=True)\n''',
    '''    agg: dict[str, tuple[str, str]] = {}\n    for col in cols:\n        pcol, scol = f"production_{col}", f"shadow_{col}"\n        if pcol in d.columns and scol in d.columns:\n            d[f"discounted_production_{col}_utility"] = _numeric(d, pcol) * d["discount"]\n            d[f"discounted_shadow_{col}_utility"] = _numeric(d, scol) * d["discount"]\n            agg[f"production_{col}_raw"] = (pcol, "sum")\n            agg[f"shadow_{col}_raw"] = (scol, "sum")\n            agg[f"production_{col}_discounted_utility"] = (\n                f"discounted_production_{col}_utility",\n                "sum",\n            )\n            agg[f"shadow_{col}_discounted_utility"] = (\n                f"discounted_shadow_{col}_utility",\n                "sum",\n            )\n    out = d.groupby("player_id", as_index=False).agg(**agg)\n    for col in cols:\n        raw_prod, raw_shadow = f"production_{col}_raw", f"shadow_{col}_raw"\n        util_prod = f"production_{col}_discounted_utility"\n        util_shadow = f"shadow_{col}_discounted_utility"\n        if raw_prod in out.columns and raw_shadow in out.columns:\n            out[f"delta_{col}_raw"] = out[raw_shadow] - out[raw_prod]\n        if util_prod in out.columns and util_shadow in out.columns:\n            out[f"delta_{col}_discounted_utility"] = out[util_shadow] - out[util_prod]\n    if "delta_apex_xp_raw" in out.columns:\n        out = out.sort_values("delta_apex_xp_raw", ascending=False)\n    return out.reset_index(drop=True)\n''',
)

replace_once(
    "tests/test_projection_audit.py",
    '''    expert_total = (\n        row["horizon_official_contribution"]\n        + row["horizon_apex_contribution"]\n        + row["horizon_airsenal_contribution"]\n        + row["horizon_market_contribution"]\n    )\n''',
    '''    expert_total = (\n        row["raw_horizon_official_contribution"]\n        + row["raw_horizon_apex_contribution"]\n        + row["raw_horizon_airsenal_contribution"]\n        + row["raw_horizon_market_contribution"]\n    )\n''',
)
replace_once(
    "tests/test_projection_audit.py",
    '''    assert np.isclose(expert_total, row["horizon_canonical_xp"])\n    assert np.isclose(component_total, row["horizon_apex_contribution"])\n''',
    '''    discounted_expert_total = (\n        row["discounted_horizon_official_contribution"]\n        + row["discounted_horizon_apex_contribution"]\n        + row["discounted_horizon_airsenal_contribution"]\n        + row["discounted_horizon_market_contribution"]\n    )\n    assert np.isclose(expert_total, row["raw_horizon_canonical_xp"])\n    assert np.isclose(discounted_expert_total, row["discounted_horizon_utility"])\n    # GW1 has discount 1.0, so the transparent Apex components reconcile exactly.\n    assert np.isclose(component_total, row["raw_horizon_apex_contribution"])\n''',
)
replace_once(
    "tests/test_projection_audit.py",
    '''def test_player_shadow_comparison_is_discounted() -> None:\n''',
    '''def test_player_shadow_comparison_separates_raw_xp_and_discounted_utility() -> None:\n''',
)
replace_once(
    "tests/test_projection_audit.py",
    '''    assert np.isclose(audit.iloc[0]["production_apex_xp"], 7.6)\n    assert np.isclose(audit.iloc[0]["shadow_apex_xp"], 9.5)\n    assert np.isclose(audit.iloc[0]["delta_apex_xp"], 1.9)\n''',
    '''    row = audit.iloc[0]\n    assert np.isclose(row["production_apex_xp_raw"], 8.0)\n    assert np.isclose(row["shadow_apex_xp_raw"], 10.0)\n    assert np.isclose(row["delta_apex_xp_raw"], 2.0)\n    assert np.isclose(row["production_apex_xp_discounted_utility"], 7.6)\n    assert np.isclose(row["shadow_apex_xp_discounted_utility"], 9.5)\n    assert np.isclose(row["delta_apex_xp_discounted_utility"], 1.9)\n''',
)
