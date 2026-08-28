from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old[:100]!r}")
    p.write_text(text.replace(old, new), encoding="utf-8")


def replace_between(path: str, start: str, end: str, transform) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    a = text.index(start)
    b = text.index(end, a)
    middle = text[a:b]
    changed = transform(middle)
    if changed == middle:
        raise RuntimeError(f"{path}: transform made no change between {start!r} and {end!r}")
    p.write_text(text[:a] + changed + text[b:], encoding="utf-8")


def prepend_once(path: str, marker: str, block: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if marker in text:
        return
    p.write_text(block.rstrip() + "\n\n" + text, encoding="utf-8")


# 1) Production configuration: one statistical authority, optional enrichments.
replace_once(
    "src/apex_fpl/config.py",
    '''    weights: dict[str, float] = field(default_factory=lambda: {\n        "official_ep": 0.2666666667,\n        "apex_model": 0.5111111111,\n        "airsenal": 0.2222222222,\n        "market": 0.0,\n    })''',
    '''    # Production statistical authority is intentionally one-hot until a challenger\n    # passes genuine prospective promotion. These are authority weights, not a hand-tuned blend.\n    weights: dict[str, float] = field(default_factory=lambda: {\n        "official_ep": 0.0,\n        "apex_model": 0.0,\n        "airsenal": 1.0,\n        "market": 0.0,\n    })''',
)
replace_once(
    "src/apex_fpl/config.py",
    '''    required_sources: list[str] = field(default_factory=lambda: [\n        "official_fpl",\n        "fpl_core_playerstats",\n        "fixture_model",\n        "airsenal",\n        "news_feeds",\n    ])''',
    '''    required_sources: list[str] = field(default_factory=lambda: [\n        "official_fpl",\n        "airsenal",\n        "news_feeds",\n    ])''',
)

replace_once(
    "config/apex.yaml",
    '''# Pre-GW1 prior policy across the three production experts that actually exist.\n# These preserve the prior 24:46:20 relative weights after removing the dormant\n# 10% market slot, so the change is semantic/auditable rather than a retune to a\n# preferred squad. Recalibration remains blocked until genuine sealed outcomes meet\n# the >=8 completed-GW / >=200-row promotion contract.\nweights:\n  official_ep: 0.2666666667\n  apex_model: 0.5111111111\n  airsenal: 0.2222222222\n  market: 0.0''',
    '''# Final production authority cutover (2026-08-28). AIrsenal is the canonical\n# statistical xP provider. Apex/Official surfaces remain diagnostics/shadow inputs.\n# Any future non-one-hot weights must be learned from immutable prospective forecasts\n# and pass the >=8 completed-GW / >=200-row promotion contract.\nweights:\n  official_ep: 0.0\n  apex_model: 0.0\n  airsenal: 1.0\n  market: 0.0''',
)
replace_once(
    "config/apex.yaml",
    '''required_sources:\n  - official_fpl\n  - fpl_core_playerstats\n  - fixture_model\n  - airsenal\n  - news_feeds''',
    '''required_sources:\n  - official_fpl\n  - airsenal\n  - news_feeds''',
)
replace_once("config/apex.yaml", "understat_team_model_mode: production", "understat_team_model_mode: shadow")

# 2) Canonical xP path: AIrsenal direct, no fallback/blend in one-hot production mode.
strict_branch = r'''    production_weights = {
        key: max(float(weights.get(key, 0.0)), 0.0) for key in EXPERT_COLUMNS
    }
    strict_airsenal_authority = (
        abs(production_weights.get("airsenal", 0.0) - 1.0) <= 1e-12
        and all(
            abs(production_weights.get(key, 0.0)) <= 1e-12
            for key in ("apex_model", "official_ep", "market")
        )
    )
    if strict_airsenal_authority:
        # This is deliberately not an ensemble. Preserve every challenger surface,
        # but canonical expected points are the validated AIrsenal number exactly.
        n = len(out)
        air = pd.to_numeric(
            out.get("airsenal_xp", pd.Series(np.nan, index=out.index)), errors="coerce"
        )
        apex = pd.to_numeric(
            out.get("apex_xp", pd.Series(np.nan, index=out.index)), errors="coerce"
        )
        official = pd.to_numeric(
            out.get("official_xp", pd.Series(np.nan, index=out.index)), errors="coerce"
        )
        market = pd.to_numeric(
            out.get("market_xp", pd.Series(np.nan, index=out.index)), errors="coerce"
        )
        out["apex_shadow_xp"] = apex
        out["production_xp"] = air
        out["xp"] = air
        out["canonical_ev_xp"] = air
        out["risk_adjusted_xp"] = air
        out["projection_provider"] = "AIrsenal"
        out["projection_authority"] = "production"
        out["apex_projection_authority"] = "shadow"

        challenger_frame = pd.concat(
            [air.rename("airsenal"), apex.rename("apex_shadow"), official.rename("official_ep"), market.rename("market")],
            axis=1,
        )
        out["expert_count"] = challenger_frame.notna().sum(axis=1).astype(int)
        out["expert_coverage"] = air.notna().astype(float)
        out["expert_disagreement_sd"] = challenger_frame.std(axis=1, ddof=0, skipna=True).fillna(0.0)
        out["model_disagreement_spread"] = (
            challenger_frame.max(axis=1, skipna=True) - challenger_frame.min(axis=1, skipna=True)
        ).fillna(0.0)
        out["model_disagreement"] = np.select(
            [out["model_disagreement_spread"] >= 3.0, out["model_disagreement_spread"] >= 1.5],
            ["high", "medium"],
            default="low",
        )
        out["configured_weight_total"] = 1.0
        out["available_or_fallback_weight"] = air.notna().astype(float)
        out["airsenal_source_absent"] = air.isna()
        out["airsenal_zero_role_conflict"] = False
        out["airsenal_abstained_role_conflict"] = False
        out["effective_weight_airsenal_fallback_apex"] = 0.0
        out["xp_expert_airsenal_fallback_apex"] = 0.0

        for key, series in {
            "apex_model": apex,
            "official_ep": official,
            "airsenal": air,
            "market": market,
        }.items():
            present = series.notna()
            out[f"source_present_{key}"] = present
            out[f"source_usable_{key}"] = present if key != "airsenal" else air.notna()
            out[f"configured_weight_{key}"] = production_weights.get(key, 0.0)
            if key == "airsenal":
                out[f"effective_weight_{key}"] = air.notna().astype(float)
                out[f"xp_expert_{key}"] = air
            else:
                out[f"effective_weight_{key}"] = 0.0
                out[f"xp_expert_{key}"] = 0.0

        out["xp_expert_apex_model_direct"] = 0.0
        out["effective_weight_apex_model_direct"] = 0.0
        out["apex_model_reliability"] = pd.to_numeric(
            out.get("apex_model_reliability", pd.Series(1.0, index=out.index)), errors="coerce"
        ).fillna(1.0)
        out["apex_reliability_conflict"] = False
        out["apex_reliability_conflict_inherited"] = False
        out["apex_reliability_conflict_direction"] = 0
        out["apex_reliability_weight_multiplier"] = 0.0
        out["independent_expert_count"] = challenger_frame[["official_ep", "airsenal", "market"]].notna().sum(axis=1).astype(int)
        out["independent_consensus_xp"] = challenger_frame[["official_ep", "airsenal", "market"]].median(axis=1, skipna=True)
        out["independent_consensus_lower"] = challenger_frame[["official_ep", "airsenal", "market"]].min(axis=1, skipna=True)
        out["independent_consensus_upper"] = challenger_frame[["official_ep", "airsenal", "market"]].max(axis=1, skipna=True)
        out["independent_consensus_margin"] = out["model_disagreement_spread"]

        minutes_conf = pd.to_numeric(
            out.get("minutes_confidence", pd.Series(0.65, index=out.index)), errors="coerce"
        ).fillna(0.65)
        role_conf = pd.to_numeric(
            out.get("role_confidence", pd.Series(0.65, index=out.index)), errors="coerce"
        ).fillna(0.65)
        source_conf = (0.55 + 0.30 * minutes_conf + 0.15 * role_conf).clip(0.05, 0.99)
        out["projection_confidence"] = np.where(air.notna(), source_conf, 0.0)
        out["forecast_uncertainty_sd"] = out["expert_disagreement_sd"]
        out["projection_sd"] = out["expert_disagreement_sd"]
        out["downside_adjusted_xp"] = np.maximum(
            air - risk_penalty * out["projection_sd"] * (1.15 - 0.30 * source_conf), 0
        )
        out["projection_floor_80"] = np.maximum(air - 1.2816 * out["projection_sd"], 0)
        out["projection_ceiling_80"] = air + 1.2816 * out["projection_sd"]
        return out
'''
replace_once(
    "src/apex_fpl/models/ensemble.py",
    '''    out = _allocate_gameweek_experts(base.copy())\n    n = len(out)''',
    '''    out = _allocate_gameweek_experts(base.copy())\n''' + strict_branch + '''    n = len(out)''',
)
replace_once(
    "src/apex_fpl/models/ensemble.py",
    '''    """Blend expert forecasts while keeping expected value separate from risk.\n\n    Missing AIrsenal rows retain the explicit Apex fallback contract.''',
    '''    """Apply projection authority, retaining legacy blending only for research configs.\n\n    With the production one-hot AIrsenal contract this function returns AIrsenal xP\n    directly and never falls back to Apex. Missing canonical rows therefore fail the\n    downstream production coverage gate. Non-production research weights retain the\n    legacy comparison behaviour.\n\n    Missing AIrsenal rows retain the explicit Apex fallback contract.''',
)

# 3) Dependency-aware data quality: Core/fixture/Understat-derived internal model warn; canonical xP stays hard.
replace_once(
    "src/apex_fpl/services/data_quality.py",
    '''# FPL can append new players between FPL Core refreshes. Core remains a required\n# enrichment source, but Official FPL is canonical identity and the complete Apex\n# projection surface is independently required.''',
    '''# FPL can append new players between FPL Core refreshes. Core is important\n# enrichment but is not a canonical-xP dependency while AIrsenal has production\n# authority. We still validate and disclose every gap; severity follows dependency.\n# Official FPL is canonical identity and the complete production projection surface is required.''',
)
replace_between(
    "src/apex_fpl/services/data_quality.py",
    "def _core_playerstats_check(",
    "def _preseason_check(",
    lambda s: s.replace("\n            True,\n", "\n            False,\n").replace("\n        True,\n", "\n        False,\n"),
)
replace_between(
    "src/apex_fpl/services/data_quality.py",
    "def _fixture_surface_check(",
    "def _projection_surface_check(",
    lambda s: s.replace("\n            True,\n", "\n            False,\n").replace("\n        True,\n", "\n        False,\n"),
)
replace_once(
    "src/apex_fpl/services/data_quality.py",
    '''                "fail",\n                True,\n                f"{strength_detail}; no validated fallback fixture model is active",''',
    '''                "fail",\n                False,\n                f"{strength_detail}; internal fixture-strength enrichment unavailable; canonical AIrsenal xP remains independent",''',
)
replace_once(
    "src/apex_fpl/services/data_quality.py",
    '''        if not (check.required and check.status == "fail")\n        and check.status in {"warning", "unavailable", "fallback"}''',
    '''        if not (check.required and check.status == "fail")\n        and check.status in {"fail", "warning", "unavailable", "fallback"}''',
)

# 4) Answer context exposes authority and optional-source warnings instead of false hard blockers.
replace_once(
    "src/apex_fpl/services/answer_context.py",
    '''REQUIRED_SOURCES = {\n    "official_fpl",\n    "fpl_core_playerstats",\n    "fixture_model",\n    "airsenal",\n    "news_feeds",\n}\n''',
    '''REQUIRED_SOURCES = {\n    "official_fpl",\n    "airsenal",\n    "news_feeds",\n}\nOPTIONAL_ENRICHMENT_SOURCES = {\n    "fpl_core_playerstats",\n    "fixture_model",\n    "understat_team_model",\n}\n''',
)
replace_once(
    "src/apex_fpl/services/answer_context.py",
    '''            "version": source.get("version"),\n        }''',
    '''            "version": source.get("version"),\n            "detail": source.get("detail"),\n        }''',
)
replace_once(
    "src/apex_fpl/services/answer_context.py",
    '''        ):\n            blockers.append(f"required/configured source is unhealthy or stale: {row['name']}")\n\n    robust = pinnacle.get("robust_cvar_scenarios")''',
    '''        ):\n            blockers.append(f"required/configured source is unhealthy or stale: {row['name']}")\n        elif row["name"] in OPTIONAL_ENRICHMENT_SOURCES and (\n            not row["configured"]\n            or not row["ok"]\n            or age is None\n            or age > MAX_SOURCE_AGE_HOURS\n        ):\n            warnings.append(f"optional enrichment is unhealthy or stale: {row['name']}")\n\n    robust = pinnacle.get("robust_cvar_scenarios")''',
)
replace_once(
    "src/apex_fpl/services/answer_context.py",
    '''    return {\n        "contract": ANSWER_CONTRACT,''',
    '''    source_by_name = {str(row.get("name")): row for row in source_health}\n    airsenal_health = source_by_name.get("airsenal", {})\n    core_health = source_by_name.get("fpl_core_playerstats", {})\n    understat_health = source_by_name.get("understat_team_model", {})\n\n    def fresh_status(row: dict[str, Any], *, fresh_label: str = "fresh") -> str:\n        if not row or not row.get("configured"):\n            return "temporarily_unavailable"\n        if not row.get("ok"):\n            detail = str(row.get("detail") or "").casefold()\n            return "schema_invalid" if any(token in detail for token in ("schema", "malformed", "empty", "invalid")) else "temporarily_unavailable"\n        age = row.get("age_hours")\n        if age is None or float(age) > MAX_SOURCE_AGE_HOURS:\n            return "stale"\n        return fresh_label\n\n    return {\n        "contract": ANSWER_CONTRACT,''',
)
replace_once(
    "src/apex_fpl/services/answer_context.py",
    '''        "source_health": source_health,\n        "diagnostics": {''',
    '''        "source_health": source_health,\n        "authority_chain": [\n            "official_fpl:factual_truth",\n            "airsenal:production_statistical_xp",\n            "football_enrichment_and_evidence",\n            "apex_optimizer:decision_authority",\n            "apex_and_challengers:shadow",\n            "prospective_calibration:promotion_judge",\n        ],\n        "official_fpl": {\n            "authority": "factual_truth",\n            "status": "fresh" if official_age is not None and official_age <= MAX_OFFICIAL_AGE_HOURS else "stale",\n            "snapshot_id": canonical_snapshot.get("snapshot_id"),\n            "retrieved_at": canonical_snapshot.get("retrieved_at"),\n            "bootstrap_sha256": canonical_snapshot.get("bootstrap_sha256"),\n            "fixtures_sha256": canonical_snapshot.get("fixtures_sha256"),\n        },\n        "canonical_projection": {\n            "provider": "AIrsenal",\n            "authority": "production",\n            "status": fresh_status(airsenal_health),\n            "generated_at": airsenal_health.get("checked_at"),\n            "version": airsenal_health.get("version"),\n            "fallback_authority": None,\n        },\n        "enrichment": {\n            "understat": {\n                "authority": "enrichment_shadow_input",\n                "status": fresh_status(understat_health, fresh_label="fresh_current_season"),\n                "version": understat_health.get("version"),\n            },\n            "fpl_core": {\n                "authority": "enrichment",\n                "status": fresh_status(core_health),\n                "version": core_health.get("version"),\n            },\n        },\n        "shadow_projections": {\n            "apex": {"provider": "Apex proprietary", "authority": "shadow", "status": "available"},\n            "openfpl": {"provider": "OpenFPL", "authority": "shadow", "status": "not_integrated"},\n        },\n        "optimizer": {"authority": "decision", "status": "optimal" if safe else "blocked"},\n        "decision": {"status": "actionable" if safe else "blocked"},\n        "diagnostics": {''',
)

# 5) Understat: HTTP 200 with empty football payload is unhealthy.
replace_once(
    "src/apex_fpl/data/understat.py",
    '''    if not isinstance(data.get("teams"), dict):\n        raise UnderstatDataError("Understat league payload has no teams object")\n    return data''',
    '''    if not isinstance(data.get("teams"), dict):\n        raise UnderstatDataError("Understat league payload has no teams object")\n    if not data["dates"]:\n        raise UnderstatDataError("Understat league payload dates list is empty")\n    if not data["teams"]:\n        raise UnderstatDataError("Understat league payload teams object is empty")\n    return data''',
)

# 6) Core refresh: install the package; keep invalidation exactly in the publication path.
replace_once(
    ".github/workflows/refresh-core-pin.yml",
    '''      - name: Install upstream verification dependencies\n        run: python -m pip install pandas requests''',
    '''      - name: Install Apex package and upstream verification dependencies\n        run: |\n          python -m pip install --upgrade pip\n          python -m pip install -e .\n          python -c "from apex_fpl.services.publication import invalidate_published_decision; print('apex package import ok')"''',
)

# 7) Prospective archive preserves shadow xP and a normalized immutable provider ledger.
replace_once(
    "src/apex_fpl/services/learning.py",
    '''            *EXPERT_COLUMNS,\n            "xp",''',
    '''            *EXPERT_COLUMNS,\n            "apex_shadow_xp",\n            "production_xp",\n            "xp",''',
)
ledger_module = '''from __future__ import annotations\n\nfrom typing import Any\n\nimport pandas as pd\n\n\nPROVIDER_COLUMNS = {\n    "AIrsenal": "airsenal_xp",\n    "Apex proprietary": "apex_shadow_xp",\n    "Official FPL EP": "official_xp",\n}\n\n\ndef provider_ledger_from_forecast(\n    forecast: pd.DataFrame,\n    *,\n    season: str,\n    source_versions: dict[str, str] | None = None,\n) -> pd.DataFrame:\n    """Normalize one frozen pre-deadline forecast into immutable provider rows."""\n    versions = source_versions or {}\n    rows: list[dict[str, Any]] = []\n    for provider, column in PROVIDER_COLUMNS.items():\n        if column not in forecast.columns:\n            continue\n        for record in forecast.to_dict("records"):\n            value = pd.to_numeric(pd.Series([record.get(column)]), errors="coerce").iloc[0]\n            if pd.isna(value):\n                continue\n            rows.append({\n                "season": season,\n                "gw": int(record["gw"]),\n                "deadline_timestamp": record.get("deadline_time"),\n                "forecast_timestamp": record.get("forecast_generated_at"),\n                "official_snapshot_id": record.get("official_snapshot_id"),\n                "player_id": int(record["player_id"]),\n                "provider": provider,\n                "provider_version": versions.get(provider, ""),\n                "authority": "production" if provider == "AIrsenal" else "shadow",\n                "xp": float(value),\n                "expected_minutes": record.get("expected_minutes"),\n                "start_probability": record.get("start_probability"),\n                "appearance_probability": record.get("appearance_probability"),\n                "position": record.get("position"),\n                "price": record.get("price"),\n                "club": record.get("team_name"),\n            })\n    return pd.DataFrame(rows)\n'''
Path("src/apex_fpl/services/prospective_ledger.py").write_text(ledger_module, encoding="utf-8")

replace_once(
    "scripts/update_learning_archive.py",
    '''from apex_fpl.services.learning import (\n    aggregate_deadline_forecast,''',
    '''from apex_fpl.services.learning import (\n    aggregate_deadline_forecast,''',
)
# import inserted separately to avoid changing the existing grouped import semantics.
replace_once(
    "scripts/update_learning_archive.py",
    '''    write_learning_report,\n)\n''',
    '''    write_learning_report,\n)\nfrom apex_fpl.services.prospective_ledger import provider_ledger_from_forecast\n''',
)
replace_once(
    "scripts/update_learning_archive.py",
    '''            if not capture_path.exists():\n                capture_path.write_bytes(csv_bytes)''',
    '''            if not capture_path.exists():\n                capture_path.write_bytes(csv_bytes)\n            source_versions = {}\n            for source in latest.get("sources") or []:\n                if not isinstance(source, dict):\n                    continue\n                name = str(source.get("name") or "")\n                if name == "airsenal":\n                    source_versions["AIrsenal"] = str(source.get("version") or "")\n                elif name == "official_fpl":\n                    source_versions["Official FPL EP"] = str(source.get("version") or "")\n            source_versions["Apex proprietary"] = str(latest.get("model_version") or "")\n            provider_ledger = provider_ledger_from_forecast(\n                frame, season=settings.season, source_versions=source_versions\n            )\n            provider_path = capture_dir / f"{bundle_id}_providers.csv"\n            if not provider_path.exists():\n                provider_path.write_text(provider_ledger.to_csv(index=False), encoding="utf-8")''',
)

# 8) Tests encode the permanent authority contract.
Path("tests/test_final_projection_authority.py").write_text('''import pandas as pd\nimport pytest\n\nfrom apex_fpl.config import Settings, load_settings\nfrom apex_fpl.data.understat import UnderstatDataError, decode_league_payload\nfrom apex_fpl.models.ensemble import blend_projection\nfrom apex_fpl.services.prospective_ledger import provider_ledger_from_forecast\n\n\ndef _weights():\n    return {"official_ep": 0.0, "apex_model": 0.0, "airsenal": 1.0, "market": 0.0}\n\n\ndef test_airsenal_is_direct_production_authority_and_apex_is_shadow():\n    base = pd.DataFrame([{\n        "player_id": 1, "gw": 2, "apex_xp": 39.0, "official_xp": 25.0,\n        "airsenal_xp": 21.0, "minutes_confidence": 0.8, "role_confidence": 0.8,\n    }])\n    row = blend_projection(base, _weights(), 0.15).iloc[0]\n    assert row["xp"] == pytest.approx(21.0)\n    assert row["production_xp"] == pytest.approx(21.0)\n    assert row["apex_shadow_xp"] == pytest.approx(39.0)\n    assert row["projection_provider"] == "AIrsenal"\n    assert row["projection_authority"] == "production"\n    assert row["apex_projection_authority"] == "shadow"\n    assert row["model_disagreement"] == "high"\n\n\ndef test_shadow_change_cannot_modify_canonical_xp():\n    base = pd.DataFrame([{"player_id": 1, "gw": 2, "apex_xp": 39.0, "airsenal_xp": 21.0}])\n    changed = base.assign(apex_xp=99.0)\n    assert blend_projection(base, _weights(), 0).iloc[0]["xp"] == pytest.approx(21.0)\n    assert blend_projection(changed, _weights(), 0).iloc[0]["xp"] == pytest.approx(21.0)\n\n\ndef test_missing_canonical_airsenal_never_falls_back_to_apex():\n    base = pd.DataFrame([{"player_id": 1, "gw": 2, "apex_xp": 39.0, "airsenal_xp": None}])\n    row = blend_projection(base, _weights(), 0).iloc[0]\n    assert pd.isna(row["xp"])\n    assert bool(row["airsenal_source_absent"])\n    assert row["effective_weight_airsenal_fallback_apex"] == 0.0\n\n\ndef test_default_and_live_config_are_one_hot_airsenal_and_core_is_optional():\n    for settings in (Settings(), load_settings()):\n        assert settings.weights == {"official_ep": 0.0, "apex_model": 0.0, "airsenal": 1.0, "market": 0.0}\n        assert "airsenal" in settings.required_sources\n        assert "fpl_core_playerstats" not in settings.required_sources\n        assert "fixture_model" not in settings.required_sources\n        assert settings.understat_team_model_mode == "shadow"\n\n\ndef test_understat_empty_http_200_payload_is_unhealthy():\n    with pytest.raises(UnderstatDataError, match="empty"):\n        decode_league_payload({"dates": [], "teams": {}})\n\n\ndef test_provider_ledger_marks_airsenal_production_and_apex_shadow():\n    forecast = pd.DataFrame([{\n        "player_id": 1, "gw": 2, "deadline_time": "2026-08-29T10:00:00+00:00",\n        "forecast_generated_at": "2026-08-28T09:00:00+00:00", "official_snapshot_id": "abc",\n        "airsenal_xp": 4.2, "apex_shadow_xp": 6.1, "official_xp": 4.0,\n        "expected_minutes": 80, "appearance_probability": 0.98, "position": "MID",\n        "price": 7.0, "team_name": "Example",\n    }])\n    ledger = provider_ledger_from_forecast(forecast, season="2026-2027", source_versions={"AIrsenal": "sha"})\n    air = ledger[ledger.provider == "AIrsenal"].iloc[0]\n    apex = ledger[ledger.provider == "Apex proprietary"].iloc[0]\n    assert air.authority == "production" and air.provider_version == "sha"\n    assert apex.authority == "shadow"\n''', encoding="utf-8")

Path("tests/test_weight_contract.py").write_text('''import pytest\n\nfrom apex_fpl.config import Settings, _validated_weights\n\n\ndef test_default_production_weights_are_qualified_airsenal_authority():\n    weights = Settings().weights\n    assert weights == {"official_ep": 0.0, "apex_model": 0.0, "airsenal": 1.0, "market": 0.0}\n    assert sum(weights.values()) == pytest.approx(1.0)\n\n\ndef test_weight_contract_rejects_non_unit_or_unknown_configuration():\n    with pytest.raises(ValueError, match="sum to 1.0"):\n        _validated_weights({"official_ep": 0.24, "apex_model": 0.46, "airsenal": 0.20, "market": 0.0})\n    with pytest.raises(ValueError, match="unknown ensemble weight keys"):\n        _validated_weights({"official_ep": 0.0, "apex_model": 0.0, "airsenal": 1.0, "market": 0.0, "phantom": 0.0})\n''', encoding="utf-8")

# Update Core data-quality expectations from blocker to explicit warning while preserving canonical projection hard failure.
p = Path("tests/test_data_quality.py")
t = p.read_text(encoding="utf-8")
t = t.replace("def test_invalid_official_strength_requires_a_validated_fallback():", "def test_invalid_internal_strength_warns_when_canonical_projection_is_complete():")
t = t.replace('''    assert not quality.ready\n    assert any("official_team_strength" in blocker for blocker in quality.blockers)''', '''    assert quality.ready\n    assert any("official_team_strength" in warning for warning in quality.warnings)''', 1)
t = t.replace("def test_required_fpl_core_player_id_coverage_is_100_percent():", "def test_fpl_core_player_id_gap_is_visible_but_optional_to_canonical_airsenal():")
t = t.replace('''    assert quality.ready is False\n    core = next(check for check in quality.checks if check.name == "fpl_core_playerstats")''', '''    assert quality.ready is True\n    core = next(check for check in quality.checks if check.name == "fpl_core_playerstats")''', 1)
t = t.replace('''    assert core.status == "fail"\n\n\ndef test_small_append_only_core_registration_lag''', '''    assert core.status == "fail"\n    assert core.required is False\n    assert any("fpl_core_playerstats" in warning for warning in quality.warnings)\n\n\ndef test_small_append_only_core_registration_lag''')
t = t.replace('''    assert quality.ready is False\n    check = next(row for row in quality.checks if row.name == "fpl_core_playerstats")\n    assert check.status == "fail"\n    assert "not an append-only trailing registration block" in check.detail''', '''    assert quality.ready is True\n    check = next(row for row in quality.checks if row.name == "fpl_core_playerstats")\n    assert check.status == "fail"\n    assert check.required is False\n    assert "not an append-only trailing registration block" in check.detail''')
p.write_text(t, encoding="utf-8")

# 9) Documentation: make this permanent architecture explicit and non-degraded.
doc = '''# Final production authority cutover — 2026-08-28\n\n**Status: permanent production architecture, not degraded mode.**\n\nAuthority is now intentionally separated:\n\n1. **Official FPL — factual truth.** Identity, club, position, price, availability, fixtures and mechanics are hard production facts.\n2. **AIrsenal — production statistical xP.** Canonical `xp` is AIrsenal exactly; no subjective rescaling, averaging or Apex fallback is allowed. Missing/stale canonical AIrsenal blocks production.\n3. **Understat + FPL Core — enrichment.** They retain historical priors, underlying stats, team strength, preseason/Elo/DefCon and shadow-model value. Their failures are explicit warnings unless a future promoted production model actually depends on them.\n4. **Current football evidence — availability/minutes/role context.** Hard evidence can exclude or invalidate; soft evidence drives uncertainty/scenarios and does not manufacture point bonuses.\n5. **Apex optimiser — decision authority.** Exact FPL mechanics, max-EV selection, near-equivalent robustness, captaincy, bench/autosubs and receding-horizon planning remain Apex's production job.\n6. **Apex proprietary xP + reproducible challengers — shadow.** Their forecasts are retained and disagreement is visible, but they cannot alter canonical xP before promotion.\n7. **Prospective calibration — judge.** Forecasts are frozen before deadlines; completed outcomes are scored out of sample. Promotion requires at least 8 genuine completed GWs, >=200 active rows, chronological holdouts, Gameweek-block bootstrap confidence, cohort diagnostics and explicit review. No automatic promotion occurs.\n\nProduction blockers follow the actual dependency graph. Optional research/enrichment failure cannot masquerade as a production failure; hard factual/canonical/mechanics/publication failures remain fail-closed. Future ensemble weights, if any, must be learned from genuine prospective frozen forecasts rather than hand selected.\n'''
for path in ["docs/APEX_ARCHITECTURE.md", "docs/APEX_CANONICAL_DECISION_POLICY.md", "docs/APEX_MASTER_CONTEXT.md", "PROJECT_STATUS.md"]:
    prepend_once(path, "Final production authority cutover — 2026-08-28", doc)

print("Final production cutover edits applied deterministically.")
