import runpy
from pathlib import Path


def _checker():
    path = Path(__file__).resolve().parents[1] / "scripts" / "check_upstreams.py"
    return runpy.run_path(str(path))


def test_upstream_check_uses_actions_token_and_stays_strict_on_failure(monkeypatch):
    module = _checker()
    observed: list[dict[str, str]] = []

    class Response:
        status_code = 403
        headers = {"X-RateLimit-Remaining": "0"}

    def fake_get(url, *, timeout, headers):
        assert url.endswith("/commits/abc")
        assert timeout == 20
        observed.append(headers)
        return Response()

    monkeypatch.setattr(module["requests"], "get", fake_get)
    failed = module["verify_upstreams"](
        {"sources": {"source": {"repository": "owner/repo", "commit": "abc"}}},
        token="actions-token",
    )

    assert observed[0]["Authorization"] == "Bearer actions-token"
    assert "HTTP 403" in failed[0]
    assert "rate-limit remaining=0" in failed[0]
