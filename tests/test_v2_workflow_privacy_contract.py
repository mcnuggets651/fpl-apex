from pathlib import Path


def _workflow(name: str) -> str:
    return Path(".github/workflows", name).read_text(encoding="utf-8")


def test_production_workflow_never_uploads_runtime_snapshot_or_raw_provider_data():
    text = _workflow("apex-v2-production.yml")
    assert "path: artifacts/v2/diagnostics/" in text
    assert "data/v2/snapshots" not in text
    assert "path: artifacts/v2/\n" not in text


def test_diagnostic_job_cannot_receive_real_fpl_credentials():
    text = _workflow("apex-v2-production.yml")
    diagnose = text.split("  diagnose:", 1)[1]
    assert 'APEX_ENABLE_PRIVATE_MANAGER_STATE: "0"' in diagnose
    assert 'FPL_SESSION_COOKIE: ""' in diagnose
    assert 'FPL_X_API_AUTHORIZATION: ""' in diagnose
    assert "secrets.FPL_SESSION_COOKIE" not in diagnose
    assert "secrets.FPL_X_API_AUTHORIZATION" not in diagnose
    assert "artifacts/v2/diagnostics/" in diagnose


def test_production_credentials_and_source_opt_in_share_one_explicit_kill_switch():
    text = _workflow("apex-v2-production.yml")
    produce = text.split("  produce:", 1)[1].split("  diagnose:", 1)[0]
    assert "APEX_V2_PRIVATE_MANAGER_ENABLED" in produce
    assert "APEX_PRIVATE_MANAGER_ENABLED" in produce
    assert "APEX_ENABLE_PRIVATE_MANAGER_STATE" in produce
    assert "Private-manager storage preflight" in produce
    assert "APEX_V2_PRIVATE_REPOSITORY" in produce
    assert "APEX_V2_PRIVATE_REPO_TOKEN" in produce
    assert "apex-v2 private-store-preflight" in produce
    assert (
        "APEX_ENABLE_PRIVATE_MANAGER_STATE: ${{ vars.APEX_V2_PRIVATE_MANAGER_ENABLED == 'true' && '1' || '0' }}"
        in produce
    )


def test_privacy_rehearsal_uses_no_real_credentials_and_uploads_only_sanitized_output():
    text = _workflow("apex-v2-privacy-rehearsal.yml")
    assert "secrets.FPL_SESSION_COOKIE" not in text
    assert "secrets.FPL_X_API_AUTHORIZATION" not in text
    assert "github.token" not in text
    assert "secrets.token_urlsafe" in text
    assert "scripts/rehearse_v2_privacy_boundary.py" in text
    assert "artifacts/v2/privacy-rehearsal/publication/diagnostics/" in text
    assert "publication/private" not in text
    assert "snapshots/" not in text


def test_evaluation_uses_private_provider_store_without_fpl_credentials():
    text = _workflow("apex-v2-evaluation.yml")
    assert "Preflight private provider evaluation store" in text
    assert "APEX_V2_PRIVATE_REPOSITORY" in text
    assert "APEX_V2_PRIVATE_REPO_TOKEN" in text
    assert "APEX_PRIVATE_GITHUB_REPOSITORY" in text
    assert "APEX_PRIVATE_GITHUB_TOKEN" in text
    assert "secrets.FPL_SESSION_COOKIE" not in text
    assert "secrets.FPL_X_API_AUTHORIZATION" not in text
