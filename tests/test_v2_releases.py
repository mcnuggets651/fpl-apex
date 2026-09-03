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
    def __init__(self, immutable=True, existing_release=None):
        self.immutable = immutable
        self.assets = []
        self.deleted = []
        # Simulates a release that already exists at the requested tag before
        # create_once is called, e.g. a draft left behind by a crashed prior
        # attempt. None means "no release at this tag yet".
        self.existing_release = existing_release

    def get(self, url, **kwargs):
        if "/releases/tags/" in url:
            if self.existing_release is not None:
                return Response(200, self.existing_release)
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


# --- Finding 1 regression tests: resumable draft publication -------------
#
# A prior attempt may have created a draft release and uploaded its asset,
# then crashed before the publish PATCH. create_once must be able to
# resume and publish that EXACT draft (never re-upload, never silently
# create a second release at the same tag) when resume_draft=True, and
# must keep refusing collisions by default otherwise.


def test_create_once_still_refuses_existing_release_by_default(tmp_path: Path):
    """Without resume_draft, an existing release at the tag -- draft or
    published -- must still be an unconditional error. This preserves the
    ordinary immutable-publication guarantee for every caller that does not
    explicitly opt into resuming a specific prior attempt."""
    asset = tmp_path / "a.json"
    asset.write_text(json.dumps({"a": 1}))
    session = Session(
        immutable=True,
        existing_release={"id": 7, "draft": True, "tag_name": "apex-v2/x/y"},
    )
    store = GitHubReleaseStore("o/r", "t", session=session)
    with pytest.raises(RuntimeError, match="already exists"):
        store.create_once(
            "apex-v2/x/y",
            {"a.json": asset},
            target_commitish="abc",
            name="x",
        )


def test_create_once_refuses_to_resume_an_already_published_release(tmp_path: Path):
    """resume_draft=True must only ever resume a DRAFT. An already-published
    (non-draft) release at the tag must still be an unconditional collision
    error -- resuming must never be able to mutate or re-publish something
    already final."""
    asset = tmp_path / "a.json"
    asset.write_text(json.dumps({"a": 1}))
    session = Session(
        immutable=True,
        existing_release={"id": 7, "draft": False, "tag_name": "apex-v2/x/y"},
    )
    store = GitHubReleaseStore("o/r", "t", session=session)
    with pytest.raises(RuntimeError, match="already exists"):
        store.create_once(
            "apex-v2/x/y",
            {"a.json": asset},
            target_commitish="abc",
            name="x",
            resume_draft=True,
        )


def test_create_once_resumes_and_publishes_an_existing_draft(tmp_path: Path):
    """The core recovery guarantee: a draft left behind by a crashed prior
    attempt, whose asset was already durably uploaded, can be published by
    a later call without re-uploading anything -- it only needs its own
    already-durable bytes to match, then completes the publish PATCH."""
    asset = tmp_path / "a.json"
    payload = json.dumps({"a": 1}).encode("utf-8")
    asset.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()

    session = Session(
        immutable=True,
        existing_release={"id": 7, "draft": True, "tag_name": "apex-v2/x/y"},
    )
    # Simulate the asset having already been durably uploaded by the prior
    # (crashed) attempt: it is already present when we ask for /assets.
    session.assets.append(
        {"name": "a.json", "digest": f"sha256:{digest}", "url": "https://api.example/assets/a.json"}
    )

    store = GitHubReleaseStore("o/r", "t", session=session)
    ref = store.create_once(
        "apex-v2/x/y",
        {"a.json": asset},
        target_commitish="abc",
        name="x",
        resume_draft=True,
    )
    assert ref.immutable is True
    assert ref.asset_hashes == {"a.json": digest}


def test_create_once_resume_rejects_asset_set_mismatch(tmp_path: Path):
    """If the caller asks to resume a draft but the draft's actual uploaded
    asset set does not match what the caller is trying to publish, this
    must fail closed rather than publish a mismatched combination."""
    asset = tmp_path / "a.json"
    asset.write_text(json.dumps({"a": 1}))
    session = Session(
        immutable=True,
        existing_release={"id": 7, "draft": True, "tag_name": "apex-v2/x/y"},
    )
    # The draft on GitHub has a DIFFERENT asset name than what we're
    # trying to publish now.
    session.assets.append(
        {"name": "unexpected.json", "digest": "sha256:00", "url": "https://api.example/assets/unexpected.json"}
    )
    store = GitHubReleaseStore("o/r", "t", session=session)
    with pytest.raises(RuntimeError, match="asset set mismatch"):
        store.create_once(
            "apex-v2/x/y",
            {"a.json": asset},
            target_commitish="abc",
            name="x",
            resume_draft=True,
        )


def test_get_draft_by_tag_returns_none_for_published_release(tmp_path: Path):
    session = Session(
        immutable=True,
        existing_release={"id": 7, "draft": False, "tag_name": "apex-v2/x/y"},
    )
    store = GitHubReleaseStore("o/r", "t", session=session)
    assert store.get_draft_by_tag("apex-v2/x/y") is None


def test_get_draft_by_tag_returns_none_when_nothing_exists(tmp_path: Path):
    store = GitHubReleaseStore("o/r", "t", session=Session(existing_release=None))
    assert store.get_draft_by_tag("apex-v2/x/y") is None


def test_get_draft_by_tag_returns_the_draft_when_present(tmp_path: Path):
    session = Session(
        immutable=True,
        existing_release={"id": 7, "draft": True, "tag_name": "apex-v2/x/y"},
    )
    store = GitHubReleaseStore("o/r", "t", session=session)
    draft = store.get_draft_by_tag("apex-v2/x/y")
    assert draft is not None
    assert draft["id"] == 7
