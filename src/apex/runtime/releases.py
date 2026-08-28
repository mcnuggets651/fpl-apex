from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
import hashlib
import json
import tarfile

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
        target_commitish: str,
        name: str,
        body: str = "",
        require_immutable: bool = True,
    ) -> ReleaseRef:
        if self._get_by_tag(tag) is not None:
            raise RuntimeError(f"immutable release tag already exists: {tag}")
        create = self.http.post(
            f"{self.api}/repos/{self.repo}/releases",
            headers=self.headers,
            json={
                "tag_name": tag,
                "target_commitish": target_commitish,
                "name": name,
                "body": body,
                "draft": True,
                "prerelease": False,
            },
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


def create_bundle_archive(
    snapshot_root: Path,
    decision_path: Path,
    output: Path,
    *,
    extra_files: dict[str, Path] | None = None,
) -> dict:
    snapshot_root = Path(snapshot_root)
    decision_path = Path(decision_path)
    output = Path(output)
    extra_files = extra_files or {}
    entries: dict[str, str] = {}
    with tarfile.open(output, "w:gz") as archive:
        for path in sorted(snapshot_root.rglob("*")):
            if path.is_file():
                arcname = f"snapshot/{path.relative_to(snapshot_root)}"
                archive.add(path, arcname=arcname)
                entries[arcname] = _sha(path)
        archive.add(decision_path, arcname="decision_bundle.json")
        entries["decision_bundle.json"] = _sha(decision_path)
        for name, path in sorted(extra_files.items()):
            archive.add(path, arcname=name)
            entries[name] = _sha(path)
    return {
        "schema_version": 1,
        "bundle_sha256": _sha(output),
        "entries": entries,
    }


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


def verify_attested_release(
    store: GitHubReleaseStore,
    release: dict,
    workdir: Path,
) -> dict:
    if not bool(release.get("immutable", False)):
        raise RuntimeError(f"release is not immutable: {release.get('tag_name')}")
    workdir = Path(workdir)
    attestation_path = download_release_asset(
        store,
        release,
        "attestation.json",
        workdir / "attestation.json",
    )
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    bundle = download_release_asset(
        store,
        release,
        "bundle.tar.gz",
        workdir / "bundle.tar.gz",
    )
    if _sha(bundle) != attestation["bundle_sha256"]:
        raise RuntimeError("release bundle hash differs from Apex attestation")
    return attestation
