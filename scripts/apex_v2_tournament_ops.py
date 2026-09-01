from __future__ import annotations

import argparse
import json
import os
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

from apex_v2_tournament_common import (
    ALL_HORIZONS, CANONICAL_PROSPECTIVE_OBSERVATION, CANDIDATE_PREFIX, DNS_INCOMPLETE_UNIVERSE, DNS_OFFICIAL_HASH, DNS_TRAINING_NOT_READY, DNS_TRAINING_READY_NO_MODEL, DNS_UPSTREAM, EVALUATION_PREFIX, FPL_BOOTSTRAP, FPL_FIXTURES, FPL_LIVE,
    GW2_DIAGNOSTIC_PREFIX, INTERNAL_PROVIDERS, PITCHSIDE_BASE, PRIVATE_TOURNAMENT_PREFIX, PROSPECTIVE_READY_CANDIDATE, SELECTION_PREFIX,
    TournamentContractError, _find_release, _load_json, _parse_utc,
    _release_asset_map, _sha256_bytes, _write_deterministic_tar_gz, _write_json,
    canonical_bytes, canonical_sha256, capture_pitchside, sha256_path,
)
from apex_v2_tournament_contract import (
    GW2_CLASSIFICATION, build_readiness, canonicalize_selected_observation,
    reliability_summary, select_latest_valid_common_seal,
)
from apex_v2_tournament_scoring import score_horizon, specialist_metrics

# Re-export the pure contract API for operations tests and audit callers.
from apex_v2_tournament_common import capture_pitchside as capture_pitchside
from apex_v2_tournament_contract import (
    build_readiness as build_readiness,
    canonicalize_selected_observation as canonicalize_selected_observation,
    reliability_summary as reliability_summary,
    select_latest_valid_common_seal as select_latest_valid_common_seal,
)

def _load_private_manager_attempt(
    *,
    private_store: Any,
    release: dict[str, Any],
    public_attempt_id: str,
    workdir: Path,
) -> dict[str, Any]:
    names = {"private_manager_attempt.json", "private_attestation.json"}
    if set(_release_asset_map(release)) != names:
        raise TournamentContractError("private manager release asset set mismatch")
    files = _download_release_files(private_store, release, names, workdir)
    attestation = _load_json(files["private_attestation.json"])
    if attestation.get("scope") != "PRIVATE_MANAGER":
        raise TournamentContractError("private manager attestation scope mismatch")
    if str(attestation.get("public_attempt_id") or "") != str(public_attempt_id):
        raise TournamentContractError("private manager release public identity mismatch")
    expected = {
        "private_manager_attempt.json": sha256_path(files["private_manager_attempt.json"])
    }
    if attestation.get("assets") != expected:
        raise TournamentContractError("private manager attestation hash mismatch")
    payload = _load_json(files["private_manager_attempt.json"])
    if str(payload.get("public_attempt_id") or "") != str(public_attempt_id):
        raise TournamentContractError("private manager attempt identity mismatch")
    return payload

def _download_release_files(store: Any, release: dict[str, Any], names: Iterable[str], root: Path) -> dict[str, Path]:
    from apex.runtime.releases import download_release_asset

    output = {}
    for name in names:
        output[name] = download_release_asset(store, release, name, root / name)
    return output


def _load_internal_private_surfaces(
    *,
    public_store: Any,
    private_store: Any,
    public_release: dict[str, Any],
    private_release: dict[str, Any],
    workdir: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, str], dict[str, Path], dict[str, Any]]:
    from apex.runtime.evaluation_archive import load_verified_private_provider_surfaces
    from apex.runtime.publication import PUBLIC_RELEASE_ASSETS_V1, verify_public_attestation

    public_assets = _release_asset_map(public_release)
    if frozenset(public_assets) != PUBLIC_RELEASE_ASSETS_V1:
        raise TournamentContractError("source final public asset set does not match frozen V2 contract")
    public_files = _download_release_files(
        public_store, public_release, PUBLIC_RELEASE_ASSETS_V1, workdir / "public"
    )
    verify_public_attestation(public_files)
    public_attempt = _load_json(public_files["public_attempt.json"])
    private_required = {"provider_forecasts.tar.gz", "provider_attestation.json"}
    if set(_release_asset_map(private_release)) != private_required:
        raise TournamentContractError("private evaluation release asset set mismatch")
    private_files = _download_release_files(private_store, private_release, private_required, workdir / "private-base")
    surfaces_by_path = load_verified_private_provider_surfaces(
        public_files["provider_forecasts.tar.gz"],
        private_files,
        public_attempt_id=str(public_attempt["public_attempt_id"]),
    )
    surfaces: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    with tarfile.open(private_files["provider_forecasts.tar.gz"], "r:gz") as archive:
        raw_by_name: dict[str, bytes] = {}
        for member in archive.getmembers():
            if not member.isfile():
                continue
            handle = archive.extractfile(member)
            if handle is None:
                raise TournamentContractError("private base provider archive member unreadable")
            raw_by_name[member.name] = handle.read()
    for path, payload in surfaces_by_path.items():
        pid = str(payload.get("provider_id") or "")
        if pid in surfaces:
            raise TournamentContractError(f"duplicate internal provider surface: {pid}")
        surfaces[pid] = payload
        raw = raw_by_name.get(path)
        if raw is None:
            raw = canonical_bytes(payload)
        hashes[pid] = _sha256_bytes(raw)
    return surfaces, hashes, public_files, public_attempt


def _seal_private_tournament_surface(
    *,
    private_store: Any,
    season: str,
    run_id: str,
    pitchside_capture: dict[str, Any],
    public_attempt_id: str,
    target_commitish: str | None,
    workdir: Path,
) -> tuple[str | None, str | None]:
    surface = pitchside_capture.get("surface")
    if not isinstance(surface, dict):
        return None, None
    raw = canonical_bytes(surface) + b"\n"
    archive = _write_deterministic_tar_gz(
        workdir / "private-tournament" / "supplemental_provider_surfaces.tar.gz",
        {"providers/pitchside.json": raw},
    )
    attestation = {
        "schema_version": 1,
        "scope": "PRIVATE_TOURNAMENT_SUPPLEMENT",
        "public_attempt_id": str(public_attempt_id),
        "run_id": str(run_id),
        "providers": {
            "providers/pitchside.json": {
                "sha256": _sha256_bytes(raw),
                "bytes": len(raw),
            }
        },
        "archive_sha256": sha256_path(archive),
    }
    attestation_path = _write_json(
        workdir / "private-tournament" / "supplemental_attestation.json",
        attestation,
    )
    tag = f"{PRIVATE_TOURNAMENT_PREFIX}/{season}/{run_id}"
    existing = _find_release(private_store.list_releases(), tag)
    if existing:
        if existing.get("immutable") is not True:
            raise TournamentContractError("existing private tournament release is mutable")
        return tag, attestation["archive_sha256"]
    private_store.create_once(
        tag,
        {
            "supplemental_provider_surfaces.tar.gz": archive,
            "supplemental_attestation.json": attestation_path,
        },
        target_commitish=target_commitish,
        name=f"Apex V2 private tournament supplement {season} {run_id}",
        body="Predeadline non-serving PITCHSIDE tournament supplement; no manager state.",
    )
    return tag, attestation["archive_sha256"]


def _load_private_tournament_surface(
    *,
    private_store: Any,
    release: dict[str, Any],
    public_attempt_id: str,
    workdir: Path,
) -> dict[str, dict[str, Any]]:
    names = {"supplemental_provider_surfaces.tar.gz", "supplemental_attestation.json"}
    if set(_release_asset_map(release)) != names:
        raise TournamentContractError("private tournament supplement asset set mismatch")
    files = _download_release_files(private_store, release, names, workdir)
    attestation = _load_json(files["supplemental_attestation.json"])
    if attestation.get("scope") != "PRIVATE_TOURNAMENT_SUPPLEMENT":
        raise TournamentContractError("private tournament supplement scope mismatch")
    if str(attestation.get("public_attempt_id") or "") != str(public_attempt_id):
        raise TournamentContractError("private tournament supplement public identity mismatch")
    if str(attestation.get("archive_sha256") or "") != sha256_path(files["supplemental_provider_surfaces.tar.gz"]):
        raise TournamentContractError("private tournament supplement archive hash mismatch")
    output = {}
    with tarfile.open(files["supplemental_provider_surfaces.tar.gz"], "r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile() or not member.name.startswith("providers/"):
                continue
            handle = archive.extractfile(member)
            if handle is None:
                raise TournamentContractError("supplement archive member unreadable")
            raw = handle.read()
            expected = (attestation.get("providers") or {}).get(member.name) or {}
            if _sha256_bytes(raw) != str(expected.get("sha256") or "") or len(raw) != int(expected.get("bytes") or -1):
                raise TournamentContractError("supplement provider hash mismatch")
            payload = json.loads(raw.decode("utf-8"))
            pid = str(payload.get("provider_id") or "")
            if not pid:
                raise TournamentContractError("supplement provider_id missing")
            output[pid] = payload
    return output


def seal_github_run(
    *,
    repo: str,
    token: str,
    private_repo: str,
    private_token: str,
    season: str,
    run_id: str,
    control_plane_sha: str,
    openfpl_readiness_path: Path,
    output: Path | None = None,
) -> dict[str, Any]:
    from apex.runtime.releases import GitHubReleaseStore

    public_store = GitHubReleaseStore(repo, token)
    private_store = GitHubReleaseStore(private_repo, private_token)
    source_tag = f"apex-v2/final/{season}/{run_id}"
    private_base_tag = f"apex-v2/private-evaluation/{season}/{run_id}"
    source_release = _find_release(public_store.list_releases(), source_tag)
    private_base_release = _find_release(private_store.list_releases(), private_base_tag)
    if source_release is None:
        raise TournamentContractError(f"source production final missing: {source_tag}")
    if private_base_release is None:
        raise TournamentContractError(f"source private evaluation release missing: {private_base_tag}")
    if source_release.get("immutable") is not True or private_base_release.get("immutable") is not True:
        raise TournamentContractError("source release pair must both be immutable")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        internal, internal_hashes, public_files, public_attempt = _load_internal_private_surfaces(
            public_store=public_store,
            private_store=private_store,
            public_release=source_release,
            private_release=private_base_release,
            workdir=root,
        )
        if str(public_attempt.get("run_id") or "") != str(run_id):
            raise TournamentContractError("source run identity mismatch")
        if str(public_attempt.get("season") or "") != str(season):
            raise TournamentContractError("source season mismatch")
        governance = _load_json(public_files["governance.json"])
        deadline = _parse_utc(str((public_attempt.get("certification") or {}).get("valid_until") or ""))
        pitchside = capture_pitchside(
            season=season,
            target_gameweek=int(public_attempt["target_gameweek"]),
            expected_official_hash=str(public_attempt["official_snapshot_sha256"]),
            deadline=deadline,
            output=root / "pitchside_capture.json",
        )
        private_tournament_tag, supplement_sha = _seal_private_tournament_surface(
            private_store=private_store,
            season=season,
            run_id=run_id,
            pitchside_capture=pitchside,
            public_attempt_id=str(public_attempt["public_attempt_id"]),
            target_commitish=None,
            workdir=root,
        )
        openfpl = _load_json(openfpl_readiness_path)
        readiness = build_readiness(
            public_attempt,
            governance,
            internal,
            source_release=source_release,
            internal_surface_sha256=internal_hashes,
            pitchside_capture=pitchside,
            openfpl_readiness=openfpl,
            private_base_release_tag=private_base_tag,
            private_tournament_release_tag=private_tournament_tag,
        )
        readiness["control_plane_sha"] = str(control_plane_sha)
        readiness["private_tournament_supplement_sha256"] = supplement_sha
        candidate_tag = f"{CANDIDATE_PREFIX}/{season}/{run_id}"
        readiness["common_seal"]["candidate_release_tag"] = candidate_tag
        readiness["readiness_sha256"] = canonical_sha256(
            {k: v for k, v in readiness.items() if k != "readiness_sha256"}
        )
        readiness_path = _write_json(root / "tournament_readiness.json", readiness)
        attestation = {
            "schema_version": 1,
            "scope": "PUBLIC_TOURNAMENT_CANDIDATE",
            "run_id": run_id,
            "public_attempt_id": public_attempt.get("public_attempt_id"),
            "readiness_sha256": sha256_path(readiness_path),
            "private_supplement_sha256": supplement_sha,
            "production_influence": "NONE",
        }
        attestation_path = _write_json(root / "tournament_attestation.json", attestation)
        existing = _find_release(public_store.list_releases(), candidate_tag)
        if existing is None:
            public_store.create_once(
                candidate_tag,
                {
                    "tournament_readiness.json": readiness_path,
                    "tournament_attestation.json": attestation_path,
                },
                target_commitish=control_plane_sha,
                name=f"Apex V2 tournament candidate {season} {run_id}",
                body=(
                    "Prospective non-serving tournament candidate. Raw provider forecasts remain private; "
                    "this release cannot change production serving authority."
                ),
            )
        elif existing.get("immutable") is not True:
            raise TournamentContractError("existing tournament candidate is mutable")
        if output:
            _write_json(output, readiness)
        return readiness


def _download_candidate(public_store: Any, release: dict[str, Any], root: Path) -> dict[str, Any]:
    names = {"tournament_readiness.json", "tournament_attestation.json"}
    if set(_release_asset_map(release)) != names:
        raise TournamentContractError("candidate release asset set mismatch")
    files = _download_release_files(public_store, release, names, root)
    readiness = _load_json(files["tournament_readiness.json"])
    attestation = _load_json(files["tournament_attestation.json"])
    if attestation.get("scope") != "PUBLIC_TOURNAMENT_CANDIDATE":
        raise TournamentContractError("candidate attestation scope mismatch")
    if str(attestation.get("readiness_sha256") or "") != sha256_path(files["tournament_readiness.json"]):
        raise TournamentContractError("candidate readiness digest mismatch")
    if str(readiness.get("readiness_sha256") or "") != canonical_sha256(
        {k: v for k, v in readiness.items() if k != "readiness_sha256"}
    ):
        raise TournamentContractError("candidate internal readiness digest mismatch")
    return readiness


def canonicalize_github(
    *,
    repo: str,
    token: str,
    season: str,
    control_plane_sha: str,
    now: datetime | None = None,
) -> list[str]:
    from apex.runtime.releases import GitHubReleaseStore

    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    store = GitHubReleaseStore(repo, token)
    releases = store.list_releases()
    candidates = [
        release
        for release in releases
        if str(release.get("tag_name") or "").startswith(f"{CANDIDATE_PREFIX}/{season}/")
        and not release.get("draft")
        and release.get("immutable") is True
    ]
    by_gameweek: dict[int, list[dict[str, Any]]] = {}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for release in candidates:
            readiness = _download_candidate(store, release, root / str(release["id"]))
            by_gameweek.setdefault(int(readiness["target_gameweek"]), []).append(readiness)
        existing_selection_releases = [
            release
            for release in releases
            if str(release.get("tag_name") or "").startswith(f"{SELECTION_PREFIX}/{season}/")
            and not release.get("draft")
        ]
        existing_gws = {
            int(str(release["tag_name"]).rsplit("gw", 1)[1])
            for release in existing_selection_releases
            if "gw" in str(release.get("tag_name") or "")
        }
        published = []
        observation_number = len(existing_selection_releases)
        for gw in sorted(by_gameweek):
            if gw < 3 or gw in existing_gws:
                continue
            selected = select_latest_valid_common_seal(
                by_gameweek[gw],
                gameweek=gw,
                as_of=now,
                require_cutoff_passed=True,
            )
            if selected is None:
                continue
            observation_number += 1
            selection = canonicalize_selected_observation(
                selected,
                observation_number=observation_number,
                selected_at=now,
            )
            path = _write_json(root / f"selection-gw{gw}.json", selection)
            attestation = _write_json(
                root / f"selection-gw{gw}-attestation.json",
                {
                    "schema_version": 1,
                    "scope": "PUBLIC_TOURNAMENT_SELECTION",
                    "selection_sha256": sha256_path(path),
                    "production_influence": "NONE",
                },
            )
            tag = f"{SELECTION_PREFIX}/{season}/gw{gw}"
            store.create_once(
                tag,
                {
                    "selection.json": path,
                    "selection_attestation.json": attestation,
                },
                target_commitish=control_plane_sha,
                name=f"Apex V2 canonical prospective observation {observation_number} GW{gw}",
                body="Selected by LAST_VALID_COMMON_PREDEADLINE_SEAL after the Official deadline.",
            )
            published.append(tag)
        return published


def _load_selection(store: Any, release: dict[str, Any], root: Path) -> dict[str, Any]:
    names = {"selection.json", "selection_attestation.json"}
    if set(_release_asset_map(release)) != names:
        raise TournamentContractError("selection release asset set mismatch")
    files = _download_release_files(store, release, names, root)
    selection = _load_json(files["selection.json"])
    attestation = _load_json(files["selection_attestation.json"])
    if attestation.get("scope") != "PUBLIC_TOURNAMENT_SELECTION":
        raise TournamentContractError("selection attestation scope mismatch")
    if str(attestation.get("selection_sha256") or "") != sha256_path(files["selection.json"]):
        raise TournamentContractError("selection digest mismatch")
    return selection


def evaluate_github(
    *,
    repo: str,
    token: str,
    private_repo: str,
    private_token: str,
    season: str,
    control_plane_sha: str,
) -> list[str]:
    from apex.runtime.releases import GitHubReleaseStore

    public_store = GitHubReleaseStore(repo, token)
    private_store = GitHubReleaseStore(private_repo, private_token)
    releases = public_store.list_releases()
    private_releases = private_store.list_releases()
    by_public_tag = {str(row.get("tag_name") or ""): row for row in releases}
    by_private_tag = {str(row.get("tag_name") or ""): row for row in private_releases}
    selection_releases = [
        row
        for row in releases
        if str(row.get("tag_name") or "").startswith(f"{SELECTION_PREFIX}/{season}/")
        and not row.get("draft")
        and row.get("immutable") is True
    ]
    published = []
    raw_bootstrap = requests.get(FPL_BOOTSTRAP, timeout=30)
    raw_bootstrap.raise_for_status()
    bootstrap = raw_bootstrap.json()
    finished = {int(e["id"]): bool(e.get("finished")) for e in bootstrap.get("events") or []}

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for sel_release in selection_releases:
            selection = _load_selection(public_store, sel_release, root / f"selection-{sel_release['id']}")
            obs = int(selection["prospective_observation_number"])
            target = int(selection["target_gameweek"])
            candidate_tag = str(selection.get("selected_candidate_tag") or "")
            candidate_release = by_public_tag.get(candidate_tag)
            if candidate_release is None:
                raise TournamentContractError(f"selected candidate release missing: {candidate_tag}")
            readiness = _download_candidate(public_store, candidate_release, root / f"candidate-{candidate_release['id']}")
            seal = readiness.get("common_seal") or {}
            run_id = str(seal.get("run_id") or "")
            source_tag = str(seal.get("source_release_tag") or "")
            private_base_tag = str(seal.get("private_base_release_tag") or "")
            private_tournament_tag = str(seal.get("private_tournament_release_tag") or "")
            source_release = by_public_tag.get(source_tag)
            private_base_release = by_private_tag.get(private_base_tag)
            if source_release is None or private_base_release is None:
                raise TournamentContractError("selected source release pair missing")
            internal, _, public_files, public_attempt = _load_internal_private_surfaces(
                public_store=public_store,
                private_store=private_store,
                public_release=source_release,
                private_release=private_base_release,
                workdir=root / f"source-{run_id}",
            )
            surfaces = dict(internal)
            if private_tournament_tag:
                supplemental_release = by_private_tag.get(private_tournament_tag)
                if supplemental_release is None:
                    raise TournamentContractError("selected private tournament supplement missing")
                surfaces.update(
                    _load_private_tournament_surface(
                        private_store=private_store,
                        release=supplemental_release,
                        public_attempt_id=str(public_attempt["public_attempt_id"]),
                        workdir=root / f"supplement-{run_id}",
                    )
                )

            manager_tag = f"apex-v2/private/{season}/{run_id}"
            manager_release = by_private_tag.get(manager_tag)
            if manager_release is None:
                raise TournamentContractError("selected private manager release missing")
            manager_attempt = _load_private_manager_attempt(
                private_store=private_store,
                release=manager_release,
                public_attempt_id=str(public_attempt["public_attempt_id"]),
                workdir=root / f"manager-{run_id}",
            )
            from apex.governance.tournament import build_model_neutral_decision_surface
            h1_decision_surface = build_model_neutral_decision_surface(
                manager_attempt,
                surfaces,
                gameweek=target,
            )
            if not h1_decision_surface:
                raise TournamentContractError("model-neutral H1 decision surface is empty")

            for horizon in ALL_HORIZONS:
                realized_gw = target + horizon - 1
                if finished.get(realized_gw) is not True:
                    continue
                eval_tag = f"{EVALUATION_PREFIX}/{season}/obs{obs}/h{horizon}"
                if eval_tag in by_public_tag:
                    continue
                entrants = (
                    readiness.get("universal_h1_league", {}).get("entrants") or []
                    if horizon == 1
                    else readiness.get("strategic_horizon_league", {}).get("entrants") or []
                )
                if not entrants:
                    continue
                live_response = requests.get(FPL_LIVE.format(gameweek=realized_gw), timeout=30)
                live_response.raise_for_status()
                live = live_response.json()
                scored = score_horizon(
                    surfaces,
                    entrants=entrants,
                    gameweek=realized_gw,
                    horizon=horizon,
                    live_payload=live,
                    decision_surface=(h1_decision_surface if horizon == 1 else None),
                )
                payload = {
                    "schema_version": 1,
                    "contract": "APEX_V2_PROSPECTIVE_TOURNAMENT_EVALUATION_V1",
                    "production_influence": "NONE",
                    "promotion_authority": False,
                    "season": season,
                    "prospective_observation_number": obs,
                    "target_gameweek": target,
                    "horizon": horizon,
                    "realized_gameweek": realized_gw,
                    "selected_candidate_tag": candidate_tag,
                    "selected_readiness_sha256": selection.get("selected_readiness_sha256"),
                    "official_live_sha256": canonical_sha256(live),
                    "entrants": list(entrants),
                    "providers": scored["providers"],
                    "all_pairwise": scored["all_pairwise"],
                    "decision_surface": {
                        "method": ("MODEL_NEUTRAL_DECISION_SURFACE_V1" if horizon == 1 else "FULL_FORECAST_OVERLAP"),
                        "player_count": scored.get("decision_surface_player_count"),
                        "player_ids_published": False,
                    },
                    "decision_quality": {
                        "status": "SEPARATE_PRIVATE_PIPELINE",
                        "private_release_tag": f"apex-v2/private-decision-quality/{season}/{run_id}",
                        "mixed_into_forecast_accuracy": False,
                    },
                    "strategic_scoring_policy": (
                        "H1 realized after target GW; strategic horizons are published only as their own future GWs finish."
                    ),
                }
                path = _write_json(root / f"eval-obs{obs}-h{horizon}.json", payload)
                attestation = _write_json(
                    root / f"eval-obs{obs}-h{horizon}-attestation.json",
                    {
                        "schema_version": 1,
                        "scope": "PUBLIC_TOURNAMENT_EVALUATION",
                        "evaluation_sha256": sha256_path(path),
                        "production_influence": "NONE",
                    },
                )
                public_store.create_once(
                    eval_tag,
                    {
                        "tournament_evaluation.json": path,
                        "tournament_evaluation_attestation.json": attestation,
                    },
                    target_commitish=control_plane_sha,
                    name=f"Apex V2 tournament observation {obs} H{horizon}",
                    body="Prospective aggregate forecast scoring only. No serving or promotion authority.",
                )
                by_public_tag[eval_tag] = {"tag_name": eval_tag, "immutable": True}
                published.append(eval_tag)
    return published


def retain_gw2_diagnostic(
    *,
    repo: str,
    token: str,
    season: str,
    control_plane_sha: str,
) -> str | None:
    """Retain GW2 evidence without converting it into a prospective observation."""
    from apex.runtime.releases import GitHubReleaseStore

    store = GitHubReleaseStore(repo, token)
    tag = f"{GW2_DIAGNOSTIC_PREFIX}/{season}/gw2"
    releases = store.list_releases()
    if _find_release(releases, tag):
        return tag
    finals = [
        row
        for row in releases
        if str(row.get("tag_name") or "").startswith(f"apex-v2/final/{season}/")
        and not row.get("draft")
        and row.get("immutable") is True
    ]
    evidence = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for release in finals:
            assets = _release_asset_map(release)
            if "public_attempt.json" not in assets:
                continue
            files = _download_release_files(store, release, ["public_attempt.json"], root / str(release["id"]))
            attempt = _load_json(files["public_attempt.json"])
            if int(attempt.get("target_gameweek") or 0) != 2:
                continue
            run_id = str(attempt.get("run_id") or "")
            evidence.append(
                {
                    "run_id": run_id,
                    "final_release_tag": release.get("tag_name"),
                    "public_attempt_id": attempt.get("public_attempt_id"),
                    "frozen_at": attempt.get("frozen_at"),
                    "evaluation_release_tag": (
                        f"apex-v2/evaluation/{season}/{run_id}"
                        if _find_release(releases, f"apex-v2/evaluation/{season}/{run_id}")
                        else None
                    ),
                }
            )
        payload = {
            "schema_version": 1,
            "contract": "APEX_V2_GW2_DIAGNOSTIC_RETENTION_V1",
            "classification": GW2_CLASSIFICATION,
            "season": season,
            "gameweek": 2,
            "production_influence": "NONE",
            "canonical_win_loss_allowed": False,
            "promotion_demotion_allowed": False,
            "retain_diagnostic_evidence": True,
            "reason": "GW2 had useful diagnostic comparisons but a provable common predeadline tournament seal is unavailable.",
            "evidence": evidence,
        }
        path = _write_json(root / "gw2_diagnostic.json", payload)
        attestation = _write_json(
            root / "gw2_diagnostic_attestation.json",
            {
                "schema_version": 1,
                "scope": "PUBLIC_GW2_DIAGNOSTIC",
                "diagnostic_sha256": sha256_path(path),
                "production_influence": "NONE",
            },
        )
        store.create_once(
            tag,
            {
                "gw2_diagnostic.json": path,
                "gw2_diagnostic_attestation.json": attestation,
            },
            target_commitish=control_plane_sha,
            name=f"Apex V2 GW2 diagnostic retention {season}",
            body="Non-canonical diagnostic/rehearsal evidence only; not an official prospective win/loss.",
        )
    return tag


def status_github(*, repo: str, token: str, season: str, output: Path) -> dict[str, Any]:
    from apex.runtime.releases import GitHubReleaseStore

    store = GitHubReleaseStore(repo, token)
    releases = store.list_releases()
    candidates = [
        row
        for row in releases
        if str(row.get("tag_name") or "").startswith(f"{CANDIDATE_PREFIX}/{season}/")
        and not row.get("draft")
        and row.get("immutable") is True
    ]
    payloads = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for row in candidates:
            payloads.append(_download_candidate(store, row, root / str(row["id"])))
    summary = reliability_summary(payloads)
    by_gw: dict[str, Any] = {}
    for payload in payloads:
        gw = str(payload.get("target_gameweek"))
        current = by_gw.get(gw)
        if current is None or _parse_utc(str((payload.get("common_seal") or {})["snapshot_frozen_at"])) > _parse_utc(str((current.get("common_seal") or {})["snapshot_frozen_at"])):
            by_gw[gw] = payload
    out = {
        "schema_version": 1,
        "contract": "APEX_V2_TOURNAMENT_STATUS_V1",
        "production_influence": "NONE",
        "season": season,
        "latest_candidate_by_gameweek": by_gw,
        "provider_reliability": summary,
    }
    _write_json(output, out)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Apex V2 operations-only prospective tournament controller")
    sub = parser.add_subparsers(dest="command", required=True)

    seal = sub.add_parser("seal-run")
    seal.add_argument("--repo", required=True)
    seal.add_argument("--private-repo", required=True)
    seal.add_argument("--season", required=True)
    seal.add_argument("--run-id", required=True)
    seal.add_argument("--control-plane-sha", required=True)
    seal.add_argument("--openfpl-readiness", type=Path, required=True)
    seal.add_argument("--output", type=Path)

    canonical = sub.add_parser("canonicalize")
    canonical.add_argument("--repo", required=True)
    canonical.add_argument("--season", required=True)
    canonical.add_argument("--control-plane-sha", required=True)

    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--repo", required=True)
    evaluate.add_argument("--private-repo", required=True)
    evaluate.add_argument("--season", required=True)
    evaluate.add_argument("--control-plane-sha", required=True)

    gw2 = sub.add_parser("retain-gw2")
    gw2.add_argument("--repo", required=True)
    gw2.add_argument("--season", required=True)
    gw2.add_argument("--control-plane-sha", required=True)

    status = sub.add_parser("status")
    status.add_argument("--repo", required=True)
    status.add_argument("--season", required=True)
    status.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required")
    private_token = os.environ.get("APEX_PRIVATE_GITHUB_TOKEN", "")

    if args.command == "seal-run":
        if not private_token:
            raise SystemExit("APEX_PRIVATE_GITHUB_TOKEN is required for seal-run")
        result = seal_github_run(
            repo=args.repo,
            token=token,
            private_repo=args.private_repo,
            private_token=private_token,
            season=args.season,
            run_id=args.run_id,
            control_plane_sha=args.control_plane_sha,
            openfpl_readiness_path=args.openfpl_readiness,
            output=args.output,
        )
    elif args.command == "canonicalize":
        result = canonicalize_github(
            repo=args.repo,
            token=token,
            season=args.season,
            control_plane_sha=args.control_plane_sha,
        )
    elif args.command == "evaluate":
        if not private_token:
            raise SystemExit("APEX_PRIVATE_GITHUB_TOKEN is required for evaluate")
        result = evaluate_github(
            repo=args.repo,
            token=token,
            private_repo=args.private_repo,
            private_token=private_token,
            season=args.season,
            control_plane_sha=args.control_plane_sha,
        )
    elif args.command == "retain-gw2":
        result = retain_gw2_diagnostic(
            repo=args.repo,
            token=token,
            season=args.season,
            control_plane_sha=args.control_plane_sha,
        )
    else:
        result = status_github(repo=args.repo, token=token, season=args.season, output=args.output)
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
