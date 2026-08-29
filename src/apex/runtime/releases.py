from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
import hashlib
import json

import requests


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class ReleaseRef:
    tag: str
    release_id: int
    html_url: str
    asset_hashes: dict[str, str]
    immutable: bool


class GitHubReleaseStore:
    """Create published production records exactly once.

    GitHub-native release immutability is mandatory. The release is created as a
    draft, all assets and GitHub-reported SHA-256 digests are verified, and only
    then is it published. If the publication is not reported immutable, the
    client best-effort removes the unusable mutable release and refuses success.

    Publication payload construction does not belong in this store. Callers must
    pass already-classified, explicitly allowlisted assets. In particular, V2 has
    no helper here that can archive an arbitrary frozen snapshot.
    """

    def __init__(
        self,
        repo: str,
        token: str,
        *,
        api: str = "https://api.github.com",
        session=None,
    ):
        self.repo = repo
        self.token = token
        self.api = api.rstrip("/")
        self.http = session or requests.Session()
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        }

    def assert_repository_policy(
        self,
        *,
        require_private: bool = False,
        require_immutable: bool = True,
        require_initialized: bool = False,
    ) -> dict:
        """Verify storage policy before any sensitive production acquisition.

        Private-manager publication must never rely on an operator remembering to
        configure repository visibility, initialization or release immutability
        correctly. A separate private release is anchored to that repository's own
        default branch; public Apex commit identity is carried cryptographically in
        the attempt payload rather than pretending the public commit exists in the
        private repository.
        """
        repository_response = self.http.get(
            f"{self.api}/repos/{self.repo}",
            headers=self.headers,
            timeout=30,
        )
        repository_response.raise_for_status()
        repository = repository_response.json()
        is_private = bool(repository.get("private", False))
        if require_private and not is_private:
            raise RuntimeError(
                "private manager store repository is not private; refuse owner-state acquisition"
            )

        default_branch = str(repository.get("default_branch") or "").strip()
        initialized = False
        if require_initialized:
            if not default_branch:
                raise RuntimeError(
                    "private manager store has no default branch; initialize it before owner-state acquisition"
                )
            branch_response = self.http.get(
                f"{self.api}/repos/{self.repo}/branches/{quote(default_branch, safe='')}",
                headers=self.headers,
                timeout=30,
            )
            if branch_response.status_code == 404:
                raise RuntimeError(
                    "private manager store has no initialized default-branch commit"
                )
            branch_response.raise_for_status()
            initialized = True

        immutable_payload = None
        immutable_enabled = False
        if require_immutable:
            immutable_response = self.http.get(
                f"{self.api}/repos/{self.repo}/immutable-releases",
                headers=self.headers,
                timeout=30,
            )
            if immutable_response.status_code == 404:
                raise RuntimeError(
                    "GitHub release immutability is not enabled for the repository"
                )
            immutable_response.raise_for_status()
            immutable_payload = immutable_response.json()
            immutable_enabled = bool(immutable_payload.get("enabled", False))
            if not immutable_enabled:
                raise RuntimeError(
                    "GitHub release immutability endpoint did not confirm enabled=true"
                )

        return {
            "repository": self.repo,
            "private": is_private,
            "default_branch": default_branch,
            "initialized": initialized if require_initialized else None,
            "immutable_releases": immutable_enabled,
            "immutability_enforced_by_owner": (
                immutable_payload.get("enforced_by_owner")
                if isinstance(immutable_payload, dict)
                else None
            ),
        }

    def _get_by_tag(self, tag: str):
        response = self.http.get(
            f"{self.api}/repos/{self.repo}/releases/tags/{tag}",
            headers=self.headers,
            timeout=30,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def _cleanup_mutable_release(self, release_id: int, tag: str) -> None:
        try:
            self.http.delete(
                f"{self.api}/repos/{self.repo}/releases/{release_id}",
                headers=self.headers,
                timeout=30,
            )
        finally:
            try:
                encoded = quote(tag, safe="/")
                self.http.delete(
                    f"{self.api}/repos/{self.repo}/git/refs/tags/{encoded}",
                    headers=self.headers,
                    timeout=30,
                )
            except Exception:
                pass

    def create_once(
        self,
        tag: str,
        files: dict[str, Path],
        *,
        target_commitish: str | None,
        name: str,
        body: str = "",
        require_immutable: bool = True,
    ) -> ReleaseRef:
        if self._get_by_tag(tag) is not None:
            raise RuntimeError(f"immutable release tag already exists: {tag}")
        create_payload = {
            "tag_name": tag,
            "name": name,
            "body": body,
            "draft": True,
            "prerelease": False,
        }
        if target_commitish is not None:
            create_payload["target_commitish"] = target_commitish
        create = self.http.post(
            f"{self.api}/repos/{self.repo}/releases",
            headers=self.headers,
            json=create_payload,
            timeout=30,
        )
        create.raise_for_status()
        release = create.json()
        release_id = int(release["id"])
        uploaded: dict[str, str] = {}
        try:
            upload_url = release["upload_url"].split("{", 1)[0]
            for asset_name, path in files.items():
                path = Path(path)
                expected = _sha(path)
                response = self.http.post(
                    upload_url,
                    headers={**self.headers, "Content-Type": "application/octet-stream"},
                    params={"name": asset_name},
                    data=path.read_bytes(),
                    timeout=120,
                )
                response.raise_for_status()
                asset = response.json()
                github_digest = str(asset.get("digest") or "")
                if github_digest and github_digest != f"sha256:{expected}":
                    raise RuntimeError(
                        f"GitHub asset digest mismatch for {asset_name}: {github_digest}"
                    )
                uploaded[asset_name] = expected
            assets_response = self.http.get(
                f"{self.api}/repos/{self.repo}/releases/{release_id}/assets",
                headers=self.headers,
                timeout=30,
            )
            assets_response.raise_for_status()
            assets = assets_response.json()
            names = {asset["name"] for asset in assets}
            if names != set(files):
                raise RuntimeError(
                    f"release asset set mismatch: {names} != {set(files)}"
                )
            for asset in assets:
                expected = uploaded[asset["name"]]
                digest = str(asset.get("digest") or "")
                if digest and digest != f"sha256:{expected}":
                    raise RuntimeError(
                        f"release asset digest mismatch for {asset['name']}: {digest}"
                    )
            publish = self.http.patch(
                f"{self.api}/repos/{self.repo}/releases/{release_id}",
                headers=self.headers,
                json={"draft": False},
                timeout=30,
            )
            publish.raise_for_status()
            published = publish.json()
            immutable = bool(published.get("immutable", False))
            if require_immutable and not immutable:
                self._cleanup_mutable_release(release_id, tag)
                raise RuntimeError(
                    "GitHub published the release as mutable. Enable repository "
                    "release immutability before any Apex V2 production attempt."
                )
            return ReleaseRef(
                tag,
                release_id,
                published.get("html_url", ""),
                uploaded,
                immutable,
            )
        except Exception:
            raise

    def list_releases(self, per_page: int = 100):
        response = self.http.get(
            f"{self.api}/repos/{self.repo}/releases",
            headers=self.headers,
            params={"per_page": per_page},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()


def write_attestation(path: Path, payload: dict) -> None:
    Path(path).write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def release_asset_map(release: dict) -> dict[str, dict]:
    return {str(asset["name"]): asset for asset in release.get("assets", [])}


def download_release_asset(
    store: GitHubReleaseStore,
    release: dict,
    name: str,
    destination: Path,
) -> Path:
    assets = release_asset_map(release)
    if name not in assets:
        raise FileNotFoundError(
            f"release {release.get('tag_name')} missing asset {name}"
        )
    asset = assets[name]
    response = store.http.get(
        asset["url"],
        headers={**store.headers, "Accept": "application/octet-stream"},
        timeout=120,
    )
    response.raise_for_status()
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(response.content)
    expected_digest = str(asset.get("digest") or "")
    if expected_digest and expected_digest != f"sha256:{_sha(destination)}":
        raise RuntimeError(f"downloaded release asset failed GitHub digest: {name}")
    return destination
