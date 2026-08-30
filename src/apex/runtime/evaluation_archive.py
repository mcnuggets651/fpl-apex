from __future__ import annotations

import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

from .snapshot import open_frozen_snapshot

PRIVATE_EVALUATION_RELEASE_ASSETS_V1 = frozenset(
    {"provider_forecasts.tar.gz", "provider_attestation.json"}
)
PRIVATE_EVALUATION_SCOPE_V1 = "PRIVATE_PROVIDER_EVALUATION"
PUBLIC_PROVENANCE_CONTRACT_V1 = "PROVENANCE_ONLY_V1"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _provider_names(snapshot) -> list[str]:
    names = sorted(
        name
        for name in snapshot.manifest.get("files", {})
        if name.startswith("providers/") and name.endswith(".json")
    )
    if not names:
        raise RuntimeError("private provider evaluation archive would be empty")
    return names


def _write_deterministic_tar_gz(
    output: Path,
    members: dict[str, bytes],
) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as zipped:
            with tarfile.open(
                fileobj=zipped,
                mode="w",
                format=tarfile.USTAR_FORMAT,
            ) as archive:
                for name, data in sorted(members.items()):
                    info = tarfile.TarInfo(name=name)
                    info.size = len(data)
                    info.mtime = 0
                    info.mode = 0o644
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    archive.addfile(info, io.BytesIO(data))
    return output


def build_private_provider_evaluation_material(
    snapshot_path: Path,
    output_dir: Path,
    *,
    public_attempt_id: str,
) -> dict[str, Path]:
    """Seal exact frozen provider surfaces for post-GW scoring.

    Raw provider rows are intentionally excluded from the public Release. This
    separate owner-private immutable record preserves the exact pre-deadline
    surfaces needed for prospective evaluation without redistributing them.
    """

    snapshot = open_frozen_snapshot(snapshot_path)
    names = _provider_names(snapshot)
    members = {name: snapshot.read_bytes(name) for name in names}
    commitments = {
        name: {
            "sha256": str(snapshot.manifest["files"][name]["sha256"]),
            "bytes": int(snapshot.manifest["files"][name]["bytes"]),
        }
        for name in names
    }

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    archive_path = _write_deterministic_tar_gz(
        root / "provider_forecasts.tar.gz",
        members,
    )
    attestation_path = _write_json(
        root / "provider_attestation.json",
        {
            "schema_version": 1,
            "scope": PRIVATE_EVALUATION_SCOPE_V1,
            "public_attempt_id": str(public_attempt_id),
            "snapshot_id": snapshot.snapshot_id,
            "archive_sha256": _sha256_file(archive_path),
            "providers": commitments,
        },
    )
    files = {
        "provider_forecasts.tar.gz": archive_path,
        "provider_attestation.json": attestation_path,
    }
    if frozenset(files) != PRIVATE_EVALUATION_RELEASE_ASSETS_V1:
        raise RuntimeError("private provider evaluation asset allowlist mismatch")
    return files


def _safe_tar_files(path: Path) -> dict[str, bytes]:
    output: dict[str, bytes] = {}
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        if any(not member.isfile() for member in members):
            raise RuntimeError("provider archive contains a non-file member")
        for member in members:
            name = str(member.name)
            parts = Path(name).parts
            if (
                not name.startswith("providers/")
                or not name.endswith(".json")
                or name.startswith("/")
                or ".." in parts
                or name in output
            ):
                raise RuntimeError("provider archive contains an unsafe member name")
            handle = archive.extractfile(member)
            if handle is None:
                raise RuntimeError("provider archive member could not be read")
            output[name] = handle.read()
    if not output:
        raise RuntimeError("provider archive contains no provider files")
    return output


def _public_provider_commitments(public_archive: Path) -> dict[str, dict]:
    commitments: dict[str, dict] = {}
    for name, data in _safe_tar_files(public_archive).items():
        try:
            payload = json.loads(data)
        except Exception as exc:
            raise RuntimeError("public provider provenance is not valid JSON") from exc
        if payload.get("publication_contract") != PUBLIC_PROVENANCE_CONTRACT_V1:
            raise RuntimeError("unsupported public provider provenance contract")
        if payload.get("forecast_rows_published") is not False:
            raise RuntimeError("public provider archive unexpectedly contains forecast rows")
        digest = str(payload.get("frozen_provider_sha256") or "").lower()
        size = payload.get("frozen_provider_bytes")
        if (
            len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
            or size is None
            or int(size) < 1
        ):
            raise RuntimeError("public provider provenance lacks a valid frozen identity")
        commitments[name] = {"sha256": digest, "bytes": int(size)}
    return commitments


def load_verified_private_provider_surfaces(
    public_provenance_archive: Path,
    private_files: dict[str, Path],
    *,
    public_attempt_id: str,
) -> dict[str, dict]:
    """Verify private rows against public pre-deadline commitments, then decode."""

    if frozenset(private_files) != PRIVATE_EVALUATION_RELEASE_ASSETS_V1:
        raise RuntimeError("private provider evaluation release asset set mismatch")
    archive_path = Path(private_files["provider_forecasts.tar.gz"])
    attestation_path = Path(private_files["provider_attestation.json"])
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    if attestation.get("schema_version") != 1:
        raise RuntimeError("unsupported private provider attestation schema")
    if attestation.get("scope") != PRIVATE_EVALUATION_SCOPE_V1:
        raise RuntimeError("private provider attestation scope mismatch")
    if str(attestation.get("public_attempt_id") or "") != str(public_attempt_id):
        raise RuntimeError("private provider archive belongs to a different public attempt")
    if str(attestation.get("archive_sha256") or "") != _sha256_file(archive_path):
        raise RuntimeError("private provider archive failed its attestation digest")

    public_commitments = _public_provider_commitments(public_provenance_archive)
    if attestation.get("providers") != public_commitments:
        raise RuntimeError("private provider attestation does not match public commitments")

    members = _safe_tar_files(archive_path)
    if set(members) != set(public_commitments):
        raise RuntimeError("private provider archive member set does not match public provenance")

    surfaces: dict[str, dict] = {}
    for name, data in sorted(members.items()):
        expected = public_commitments[name]
        if _sha256_bytes(data) != expected["sha256"] or len(data) != expected["bytes"]:
            raise RuntimeError("private provider surface does not match public frozen identity")
        try:
            payload = json.loads(data)
        except Exception as exc:
            raise RuntimeError("private provider surface is not valid JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
            raise RuntimeError("private provider surface schema is incomplete")
        surfaces[name] = payload
    return surfaces
