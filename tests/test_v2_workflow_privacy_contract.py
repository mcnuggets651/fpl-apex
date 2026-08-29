from pathlib import Path


def _workflow(name: str) -> str:
    return Path(".github/workflows", name).read_text(encoding="utf-8")


def test_production_workflow_never_uploads_runtime_snapshot_or_raw_provider_data():
    text = _workflow("apex-v2-production.yml")
    assert "path: artifacts/v2/diagnostics/" in text
    assert "data/v2/snapshots" not in text
    assert "acquisition/providers" not in text.split(
        "- name: Upload sanitized diagnostic snapshot", 1
    )[-1]
    assert "path: artifacts/v2/\n" not in text


def test_diagnostic_job_cannot_receive_real_fpl_credentials():
    text = _workflow("apex-v2-production.yml")
    diagnose = text.split("  diagnose:", 1)[1]
    assert 'FPL_SESSION_COOKIE: ""' in diagnose
    assert 'FPL_X_API_AUTHORIZATION: ""' in diagnose
    assert "secrets.FPL_SESSION_COOKIE" not in diagnose
    assert "secrets.FPL_X_API_AUTHORIZATION" not in diagnose
    assert "artifacts/v2/diagnostics/" in diagnose


def test_production_credentials_are_behind_explicit_repository_kill_switch():
    text = _workflow("apex-v2-production.yml")
    assert "APEX_V2_PRIVATE_MANAGER_ENABLED" in text
    assert "APEX_PRIVATE_MANAGER_ENABLED" in text
    assert "APEX_ENABLE_PRIVATE_MANAGER_STATE" not in text
    # Source-level opt-in intentionally remains unwired until the real Actions
    # fake-credential rehearsal passes.


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
