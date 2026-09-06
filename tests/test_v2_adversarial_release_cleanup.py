from __future__ import annotations

from pathlib import Path

import pytest

from apex.runtime.releases import GitHubReleaseStore


class Response:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._payload


class FailingUploadSession:
    def __init__(self):
        self.deleted: list[str] = []

    def get(self, url, **kwargs):
        if "/releases/tags/" in url:
            return Response(404, {})
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url, **kwargs):
        if url.endswith("/releases"):
            return Response(
                201,
                {
                    "id": 42,
                    "upload_url": "https://uploads.example/assets{?name}",
                },
            )
        return Response(500, {"message": "synthetic upload failure"})

    def delete(self, url, **kwargs):
        self.deleted.append(url)
        return Response(204, None)


def test_failed_asset_upload_cleans_draft_release_and_tag(tmp_path: Path):
    asset = tmp_path / "asset.json"
    asset.write_text("{}\n", encoding="utf-8")
    session = FailingUploadSession()
    store = GitHubReleaseStore("owner/repo", "token", session=session)

    with pytest.raises(RuntimeError, match="http 500"):
        store.create_once(
            "apex-v2/final/2026-2027/run-1",
            {"asset.json": asset},
            target_commitish="abc123",
            name="Apex final",
        )

    assert any("/releases/42" in url for url in session.deleted)
    assert any("/git/refs/tags/" in url for url in session.deleted)
