from pathlib import Path

FROZEN = "99cc7b51b0cff45462b567084cb1844cfe0a456f"
ROOT = Path(__file__).parents[1]


def test_production_keeps_frozen_engine_and_uses_derived_runtime_config():
    text = (ROOT / ".github/workflows/apex-v2-daily-production.yml").read_text()
    assert f'FROZEN_APEX_SHA: "{FROZEN}"' in text
    assert f'APEX_CODE_SHA: "{FROZEN}"' in text
    assert 'git show "$CONTROL_PLANE_SHA:scripts/apex_v2_shadow_provider_ops.py"' in text
    assert '--source config/apex_v2.yaml' in text
    assert '--output "$RUNNER_TEMP/apex_v2_runtime.yaml"' in text
    assert '--config "$RUNNER_TEMP/apex_v2_runtime.yaml"' in text
    assert 'Acquire Dastan H1 shadow in isolated provider runtime' in text
    assert 'Generate fresh AIrsenal candidate' in text


def test_external_health_workflow_has_no_production_or_manager_authority():
    text = (ROOT / ".github/workflows/apex-v2-shadow-health.yml").read_text()
    forbidden = [
        "FPL_SESSION_COOKIE",
        "FPL_X_API_AUTHORIZATION",
        "FPL_REFRESH_TOKEN",
        "apex-v2 solve",
        "apex-v2 publish",
        "workflow_dispatch production",
        "APEX_PRIVATE_GITHUB_TOKEN",
    ]
    for token in forbidden:
        assert token not in text
    assert "contents: read" in text
    assert "pitchside-health" in text
    assert "openfpl-readiness" in text
