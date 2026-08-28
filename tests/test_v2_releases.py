from pathlib import Path
import hashlib
import json

import pytest

from apex.runtime.releases import GitHubReleaseStore


class Response:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        return self._payload


class Session:
    def __init__(self, immutable=True):
        self.immutable = immutable
        self.assets = []
        self.deleted = []

    def get(self, url, **kwargs):
        if "/releases/tags/" in url:
            return Response(404, {})
        if url.endswith("/assets"):
            return Response(200, list(self.assets))
        return Response(200, [])

    def post(self, url, **kwargs):
        if url.endswith("/releases"):
            return Response(
                201,
                {
                    "id": 7,
                    "upload_url": "https://uploads.example/assets{?name}",
                },
            )
        name = kwargs["params"]["name"]
        digest = hashlib.sha256(kwargs["data"]).hexdigest()
        asset = {
            "name": name,
            "digest": f"sha256:{digest}",
            "url": f"https://api.example/assets/{name}",
        }
        self.assets.append(asset)
        return Response(201, asset)

    def patch(self, url, **kwargs):
        return Response(
            200,
            {
                "id": 7,
                "html_url": "https://github.example/release/7",
                "immutable": self.immutable,
            },
        )

    def delete(self, url, **kwargs):
        self.deleted.append(url)
        return Response(204, None)


def test_release_requires_github_native_immutability(tmp_path: Path):
    asset = tmp_path / "a.json"
    asset.write_text(json.dumps({"a": 1}))
    session = Session(immutable=False)
    store = GitHubReleaseStore("o/r", "t", session=session)
    with pytest.raises(RuntimeError, match="release immutability"):
        store.create_once(
            "apex-v2/final/s/r",
            {"a.json": asset},
            target_commitish="abc",
            name="x",
        )
    assert session.deleted


def test_release_accepts_native_immutable_publication(tmp_path: Path):
    asset = tmp_path / "a.json"
    asset.write_text(json.dumps({"a": 1}))
    store = GitHubReleaseStore("o/r", "t", session=Session(immutable=True))
    ref = store.create_once(
        "apex-v2/final/s/r",
        {"a.json": asset},
        target_commitish="abc",
        name="x",
    )
    assert ref.immutable is True
