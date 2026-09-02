from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import timezone
from pathlib import Path
from typing import Any

from apex.runtime.releases import GitHubReleaseStore
from apex.runtime.serde import official_from_dict, team_from_dict
from apex_v2_decision_quality_ops import (
    FROZEN_APEX_SHA,
    LAB_ASSETS,
    LAB_CONTRACT,
    LAB_PREFIX,
    _availability_overlay,
    _complete_expected_points,
    _contiguous_horizon,
    _decision_dict,
    _decision_signature,
    _hard_exclusions_from_public_evidence,
    _hybrid_h1_then_airsenal,
    _load_candidate_context,
    _load_private_payload,
    _production_surface,
    _utc_now,
    _variant,
    _write_private_release,
    publish_completed_decision_quality,
    publish_decision_edge_learning,
    score_completed_labs,
)
from apex_v2_tournament_common import (
    CANDIDATE_PREFIX,
    TournamentContractError,
    _find_release,
    _parse_utc,
    canonical_sha256,
)
from apex_v2_tournament_ops import _download_candidate

TASK_PREFIX = "apex-v2/private-decision-lab-task"
TASK_CONTRACT = "APEX_V2_PRIVATE_DECISION_LAB_TASK_V1"
TASK_ASSETS = frozenset({"decision_lab_task.json", "decision_lab_task_attestation.json"})
TASK_SCOPE = "PRIVATE_PROSPECTIVE_DECISION_LAB_TASK"
PARALLEL_CONTROLLER_CONTRACT = "APEX_V2_PARALLEL_DECISION_LAB_CONTROLLER_V1"
TASK_KINDS = frozenset(
    {
        "BASELINE_REPRODUCTION",
        "H1_MECHANICS_ON_PRODUCTION_SQUAD",
        "CHALLENGER_H1_AIRSENAL_H2_PLUS",
        "CHALLENGER_AVAILABILITY_ON_AIRSENAL_XP",
        "PURE_PROVIDER_CONTIGUOUS_PLAN",
    }
)


def _stores() -> tuple[GitHubReleaseStore, GitHubReleaseStore]:
    public_repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    public_token = os.environ.get("GITHUB_TOKEN", "").strip()
    private_repo = os.environ.get("APEX_PRIVATE_GITHUB_REPOSITORY", "").strip()
    private_token = os.environ.get("APEX_PRIVATE_GITHUB_TOKEN", "").strip()
    if not all((public_repo, public_token, private_repo, private_token)):
        raise RuntimeError("parallel decision lab requires complete public/private credentials")
    if public_repo == private_repo:
        raise RuntimeError("parallel decision lab private repository must be separate")
    public_store = GitHubReleaseStore(public_repo, public_token)
    private_store = GitHubReleaseStore(private_repo, private_token)
    private_store.assert_repository_policy(
        require_private=True, require_immutable=True, require_initialized=True
    )
    return public_store, private_store


def _safe_provider_token(provider_id: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", provider_id.lower()).strip("-") or "provider"
    suffix = hashlib.sha256(provider_id.encode("utf-8")).hexdigest()[:8]
    return f"{base[:32]}-{suffix}"


def _task_id(kind: str, provider_id: str | None = None) -> str:
    names = {
        "BASELINE_REPRODUCTION": "baseline",
        "H1_MECHANICS_ON_PRODUCTION_SQUAD": "h1-mechanics",
        "CHALLENGER_H1_AIRSENAL_H2_PLUS": "h1-future",
        "CHALLENGER_AVAILABILITY_ON_AIRSENAL_XP": "availability",
        "PURE_PROVIDER_CONTIGUOUS_PLAN": "pure-plan",
    }
    if kind not in names:
        raise TournamentContractError(f"unknown decision-lab task kind: {kind}")
    if provider_id is None:
        if kind != "BASELINE_REPRODUCTION":
            raise TournamentContractError("challenger task requires provider id")
        return names[kind]
    return f"{names[kind]}--{_safe_provider_token(provider_id)}"


def _task_release_tag(*, season: str, run_id: str, control_plane_sha: str, task_id: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", control_plane_sha):
        raise TournamentContractError("control-plane SHA must be an exact 40-char git SHA")
    if not re.fullmatch(r"[a-z0-9-]+(?:--[a-z0-9-]+)?", task_id):
        raise TournamentContractError("unsafe task id")
    return f"{TASK_PREFIX}/{season}/{run_id}/{control_plane_sha[:12]}/{task_id}"


def _candidate_releases(public_releases: list[dict[str, Any]], season: str) -> list[dict[str, Any]]:
    prefix = f"{CANDIDATE_PREFIX}/{season}/"
    return sorted(
        [
            release
            for release in public_releases
            if str(release.get("tag_name") or "").startswith(prefix)
            and not release.get("draft")
            and release.get("immutable") is True
        ],
        key=lambda row: str(row.get("published_at") or ""),
    )


def _load_context(
    *,
    public_store: Any,
    private_store: Any,
    public_releases: list[dict[str, Any]],
    private_releases: list[dict[str, Any]],
    candidate_release: dict[str, Any],
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]], dict[str, str], dict[str, Path]]:
    readiness = _download_candidate(public_store, candidate_release, root / "candidate")
    manager_attempt, surfaces, hashes, public_files = _load_candidate_context(
        public_store=public_store,
        private_store=private_store,
        public_releases=public_releases,
        private_releases=private_releases,
        candidate_release=candidate_release,
        readiness=readiness,
        root=root / "context",
    )
    return readiness, manager_attempt, surfaces, hashes, public_files


def _planning_horizon(
    *, private_attempt: dict[str, Any], airsenal: dict[str, Any], decision_universe: frozenset[int]
) -> int:
    available = _contiguous_horizon(
        airsenal,
        required_ids=decision_universe,
        maximum=max((int(value) for value in airsenal.get("supported_horizons") or [1])),
    )
    baseline = private_attempt.get("system_decision") or {}
    transfer_plan = private_attempt.get("transfer_plan") or []
    if str(baseline.get("decision_mode") or "") == "TRANSFER_HORIZON":
        if not isinstance(transfer_plan, list) or not transfer_plan:
            raise TournamentContractError("parallel lab cannot recover immutable planning horizon")
        horizon = len(transfer_plan)
    else:
        horizon = available
    if horizon < 2 or horizon > available:
        raise TournamentContractError("parallel lab planning horizon is incompatible with AIrsenal coverage")
    return horizon


def _derive_plan(
    *,
    readiness: dict[str, Any],
    private_attempt: dict[str, Any],
    surfaces: dict[str, dict[str, Any]],
    surface_hashes: dict[str, str],
    public_files: dict[str, Path],
    control_plane_sha: str,
) -> dict[str, Any]:
    if readiness.get("tournament_ready") is not True:
        raise TournamentContractError("parallel lab requires tournament-ready candidate")
    if readiness.get("production_influence") != "NONE":
        raise TournamentContractError("candidate crossed production boundary")
    seal = readiness.get("common_seal") or {}
    if seal.get("eligible_common_predeadline_candidate") is not True:
        raise TournamentContractError("parallel lab requires common predeadline candidate")
    canonical = private_attempt.get("canonical_forecast") or {}
    official = official_from_dict(canonical.get("official") or {})
    team_raw = private_attempt.get("team_state")
    if not isinstance(team_raw, dict):
        raise TournamentContractError("parallel lab requires exact authenticated team state")
    team = team_from_dict(team_raw)
    baseline = private_attempt.get("system_decision")
    if not isinstance(baseline, dict):
        raise TournamentContractError("parallel lab requires immutable production decision")
    airsenal = surfaces.get("airsenal")
    if airsenal is None:
        raise TournamentContractError("parallel lab requires sealed AIrsenal surface")
    if str((readiness.get("production") or {}).get("serving_provider_by_horizon", {}).get("1")) != "airsenal":
        raise TournamentContractError("parallel lab baseline serving provider is not AIrsenal")
    entrants = [str(value) for value in (readiness.get("universal_h1_league") or {}).get("entrants") or []]
    if "airsenal" not in entrants:
        raise TournamentContractError("parallel lab H1 field lacks AIrsenal")
    missing = [provider_id for provider_id in entrants if provider_id not in surfaces]
    if missing:
        raise TournamentContractError("parallel lab missing sealed H1 surface: " + ", ".join(missing))
    provider_meta = readiness.get("providers") or {}
    for provider_id in entrants:
        expected = str((provider_meta.get(provider_id) or {}).get("artifact_sha256") or "")
        observed = str(surface_hashes.get(provider_id) or "")
        if expected and expected != observed:
            raise TournamentContractError(f"parallel lab provider hash mismatch: {provider_id}")
    decision_universe = official.decision_universe(set(team.squad_ids))
    max_horizon = _planning_horizon(
        private_attempt=private_attempt, airsenal=airsenal, decision_universe=decision_universe
    )
    target_gameweek = int(readiness["target_gameweek"])
    exclusions = _hard_exclusions_from_public_evidence(public_files, gameweek=target_gameweek)
    private_context_hash = canonical_sha256(
        {
            "team_state": team_raw,
            "system_decision": baseline,
            "transfer_plan": private_attempt.get("transfer_plan") or [],
        }
    )
    tasks: list[dict[str, Any]] = [
        {
            "task_id": _task_id("BASELINE_REPRODUCTION"),
            "kind": "BASELINE_REPRODUCTION",
            "provider_id": "airsenal",
            "source_surface_hashes": {"airsenal": surface_hashes["airsenal"]},
        }
    ]
    experiment_matrix: dict[str, dict[str, str]] = {}
    for provider_id in entrants:
        if provider_id == "airsenal":
            continue
        statuses = {
            "h1_mechanics": "PENDING_TASK",
            "h1_plus_airsenal_future": "PENDING_TASK",
            "availability_on_airsenal": "PENDING_TASK",
            "pure_provider_plan": "PENDING_TASK",
        }
        experiment_matrix[provider_id] = statuses
        challenger = surfaces[provider_id]
        if not _complete_expected_points(
            challenger, horizon=1, required_ids=decision_universe
        ):
            for key in statuses:
                statuses[key] = "NOT_SCOREABLE_INCOMPLETE_H1_XP"
            continue
        tasks.append(
            {
                "task_id": _task_id("H1_MECHANICS_ON_PRODUCTION_SQUAD", provider_id),
                "kind": "H1_MECHANICS_ON_PRODUCTION_SQUAD",
                "provider_id": provider_id,
                "source_surface_hashes": {
                    provider_id: surface_hashes[provider_id],
                    "airsenal": surface_hashes["airsenal"],
                },
            }
        )
        tasks.append(
            {
                "task_id": _task_id("CHALLENGER_H1_AIRSENAL_H2_PLUS", provider_id),
                "kind": "CHALLENGER_H1_AIRSENAL_H2_PLUS",
                "provider_id": provider_id,
                "source_surface_hashes": {
                    provider_id: surface_hashes[provider_id],
                    "airsenal": surface_hashes["airsenal"],
                },
            }
        )
        try:
            _, overlay_fields = _availability_overlay(
                provider_id=provider_id,
                challenger=challenger,
                airsenal=airsenal,
                required_ids=decision_universe,
                max_horizon=max_horizon,
            )
        except TournamentContractError:
            statuses["availability_on_airsenal"] = "NOT_SCOREABLE_NO_COMPLETE_AVAILABILITY_FIELD"
        else:
            tasks.append(
                {
                    "task_id": _task_id("CHALLENGER_AVAILABILITY_ON_AIRSENAL_XP", provider_id),
                    "kind": "CHALLENGER_AVAILABILITY_ON_AIRSENAL_XP",
                    "provider_id": provider_id,
                    "overlay_fields": overlay_fields,
                    "source_surface_hashes": {
                        provider_id: surface_hashes[provider_id],
                        "airsenal": surface_hashes["airsenal"],
                    },
                }
            )
        provider_horizon = _contiguous_horizon(
            challenger, required_ids=decision_universe, maximum=max_horizon
        )
        if provider_horizon >= 2:
            tasks.append(
                {
                    "task_id": _task_id("PURE_PROVIDER_CONTIGUOUS_PLAN", provider_id),
                    "kind": "PURE_PROVIDER_CONTIGUOUS_PLAN",
                    "provider_id": provider_id,
                    "provider_horizon": provider_horizon,
                    "source_surface_hashes": {provider_id: surface_hashes[provider_id]},
                }
            )
        else:
            statuses["pure_provider_plan"] = "NOT_SUPPORTED_H1_ONLY_OR_INCOMPLETE_H2"
    source = {
        "season": readiness["season"],
        "target_gameweek": target_gameweek,
        "run_id": seal["run_id"],
        "public_attempt_id": seal["public_attempt_id"],
        "candidate_release_tag": seal["candidate_release_tag"],
        "candidate_readiness_sha256": readiness["readiness_sha256"],
        "snapshot_id": seal["snapshot_id"],
        "official_snapshot_sha256": seal["official_snapshot_sha256"],
        "deadline": seal["deadline"],
    }
    plan_binding = {
        "contract": PARALLEL_CONTROLLER_CONTRACT,
        "control_plane_sha": control_plane_sha,
        "source": source,
        "max_horizon": max_horizon,
        "private_context_sha256": private_context_hash,
        "hard_exclusion_sha256": canonical_sha256(sorted(exclusions)),
        "hard_exclusion_count": len(exclusions),
        "tasks": tasks,
        "experiment_matrix": experiment_matrix,
    }
    plan_binding["plan_sha256"] = canonical_sha256(plan_binding)
    return {
        **plan_binding,
        "decision_universe_player_count": len(decision_universe),
        "decision_universe_player_ids_published": False,
    }


def _task_fingerprint(plan: dict[str, Any], task: dict[str, Any]) -> str:
    return canonical_sha256(
        {
            "contract": TASK_CONTRACT,
            "control_plane_sha": plan["control_plane_sha"],
            "source": plan["source"],
            "plan_sha256": plan["plan_sha256"],
            "private_context_sha256": plan["private_context_sha256"],
            "hard_exclusion_sha256": plan["hard_exclusion_sha256"],
            "max_horizon": plan["max_horizon"],
            "task": task,
        }
    )


def _release_predeadline(release: dict[str, Any], payload: dict[str, Any], deadline_text: str) -> bool:
    deadline = _parse_utc(deadline_text)
    published_at = str(release.get("published_at") or "")
    sealed_at = str(payload.get("sealed_at") or "")
    if not published_at or not sealed_at:
        return False
    return _parse_utc(published_at) < deadline and _parse_utc(sealed_at) < deadline


def _load_task_release(
    *, private_store: Any, release: dict[str, Any], expected_fingerprint: str, deadline: str, workdir: Path
) -> dict[str, Any]:
    payload = _load_private_payload(
        store=private_store,
        release=release,
        payload_name="decision_lab_task.json",
        attestation_name="decision_lab_task_attestation.json",
        expected_assets=TASK_ASSETS,
        scope=TASK_SCOPE,
        workdir=workdir,
    )
    if payload.get("contract") != TASK_CONTRACT:
        raise TournamentContractError("decision-lab staging contract mismatch")
    if str(payload.get("task_fingerprint_sha256") or "") != expected_fingerprint:
        raise TournamentContractError("immutable decision-lab task fingerprint mismatch")
    if not _release_predeadline(release, payload, deadline):
        raise TournamentContractError("decision-lab staging task was not sealed before deadline")
    return payload


def _find_candidate_by_tag(releases: list[dict[str, Any]], tag: str) -> dict[str, Any]:
    release = _find_release(releases, tag)
    if release is None or release.get("immutable") is not True:
        raise TournamentContractError(f"candidate release missing or mutable: {tag}")
    return release


def prepare(*, season: str, control_plane_sha: str) -> dict[str, Any]:
    public_store, private_store = _stores()
    public_releases = public_store.list_releases()
    private_releases = private_store.list_releases()
    private_by_tag = {
        str(row.get("tag_name") or ""): row for row in private_releases if not row.get("draft")
    }
    matrix: list[dict[str, str]] = []
    plans: list[dict[str, Any]] = []
    now = _utc_now()
    with tempfile.TemporaryDirectory(prefix="apex-parallel-plan-") as tmp:
        root = Path(tmp)
        for candidate in _candidate_releases(public_releases, season):
            readiness = _download_candidate(public_store, candidate, root / f"candidate-{candidate['id']}")
            if readiness.get("tournament_ready") is not True:
                continue
            seal = readiness.get("common_seal") or {}
            if seal.get("eligible_common_predeadline_candidate") is not True:
                continue
            deadline = _parse_utc(str(seal.get("deadline") or ""))
            if now >= deadline:
                continue
            run_id = str(seal.get("run_id") or "")
            lab_tag = f"{LAB_PREFIX}/{season}/{run_id}"
            existing_lab = private_by_tag.get(lab_tag)
            if existing_lab is not None:
                _load_private_payload(
                    store=private_store,
                    release=existing_lab,
                    payload_name="decision_lab.json",
                    attestation_name="decision_lab_attestation.json",
                    expected_assets=LAB_ASSETS,
                    scope="PRIVATE_PROSPECTIVE_DECISION_LAB",
                    workdir=root / f"existing-lab-{run_id}",
                )
                continue
            readiness, manager_attempt, surfaces, hashes, public_files = _load_context(
                public_store=public_store,
                private_store=private_store,
                public_releases=public_releases,
                private_releases=private_releases,
                candidate_release=candidate,
                root=root / f"context-{run_id}",
            )
            plan = _derive_plan(
                readiness=readiness,
                private_attempt=manager_attempt,
                surfaces=surfaces,
                surface_hashes=hashes,
                public_files=public_files,
                control_plane_sha=control_plane_sha,
            )
            plans.append(
                {
                    "run_id": run_id,
                    "candidate_release_tag": plan["source"]["candidate_release_tag"],
                    "task_count": len(plan["tasks"]),
                    "plan_sha256": plan["plan_sha256"],
                }
            )
            for task in plan["tasks"]:
                tag = _task_release_tag(
                    season=season,
                    run_id=run_id,
                    control_plane_sha=control_plane_sha,
                    task_id=task["task_id"],
                )
                prior = private_by_tag.get(tag)
                fingerprint = _task_fingerprint(plan, task)
                if prior is not None:
                    _load_task_release(
                        private_store=private_store,
                        release=prior,
                        expected_fingerprint=fingerprint,
                        deadline=plan["source"]["deadline"],
                        workdir=root / f"prior-{run_id}-{task['task_id']}",
                    )
                    continue
                matrix.append(
                    {
                        "candidate_tag": plan["source"]["candidate_release_tag"],
                        "task_id": task["task_id"],
                    }
                )
    return {
        "schema_version": 1,
        "contract": PARALLEL_CONTROLLER_CONTRACT,
        "mode": "PREPARE",
        "production_influence": "NONE",
        "serving_authorized": False,
        "private_manager_state_in_matrix": False,
        "matrix": {"include": matrix},
        "has_tasks": bool(matrix),
        "candidate_plans": plans,
    }


def _optimise_once(*, official: Any, surface: dict[str, Any], team: Any, max_horizon: int, exclusions: frozenset[int]) -> Any:
    from apex.decision.transfers import optimise_transfer_horizon

    return optimise_transfer_horizon(
        official,
        _production_surface(surface),
        team,
        max_horizon=max_horizon,
        excluded_h1=exclusions,
    )


def _solve_task_from_context(
    *,
    plan: dict[str, Any],
    task: dict[str, Any],
    private_attempt: dict[str, Any],
    surfaces: dict[str, dict[str, Any]],
    surface_hashes: dict[str, str],
    public_files: dict[str, Path],
) -> dict[str, Any]:
    if task["kind"] not in TASK_KINDS:
        raise TournamentContractError("unsupported decision-lab task kind")
    canonical = private_attempt.get("canonical_forecast") or {}
    official = official_from_dict(canonical.get("official") or {})
    team = team_from_dict(private_attempt["team_state"])
    baseline = private_attempt["system_decision"]
    decision_universe = official.decision_universe(set(team.squad_ids))
    exclusions = _hard_exclusions_from_public_evidence(
        public_files, gameweek=int(plan["source"]["target_gameweek"])
    )
    if canonical_sha256(sorted(exclusions)) != plan["hard_exclusion_sha256"]:
        raise TournamentContractError("decision-lab hard-exclusion binding changed")
    kind = task["kind"]
    provider_id = str(task["provider_id"])
    result: dict[str, Any] = {"status": "SEALED_PREDEADLINE", "variant": None}
    if kind == "BASELINE_REPRODUCTION":
        solved = _optimise_once(
            official=official,
            surface=surfaces["airsenal"],
            team=team,
            max_horizon=int(plan["max_horizon"]),
            exclusions=exclusions,
        )
        if solved.decision is None:
            raise TournamentContractError("baseline reproduction produced no decision")
        observed = _decision_signature(_decision_dict(solved.decision))
        expected = _decision_signature(baseline)
        if observed != expected:
            raise TournamentContractError("parallel baseline reproduction does not match production")
        result["status"] = "BASELINE_VERIFIED"
        result["decision_signature_sha256"] = canonical_sha256(observed)
        return result
    challenger = surfaces[provider_id]
    if kind == "H1_MECHANICS_ON_PRODUCTION_SQUAD":
        from apex.decision.mechanics import decision_from_fixed_squad

        baseline_squad = tuple(int(value) for value in baseline.get("squad_ids") or [])
        decision = decision_from_fixed_squad(
            official,
            _production_surface(challenger),
            baseline_squad,
            horizon=1,
            transfers_in=tuple(int(value) for value in baseline.get("transfers_in") or []),
            transfers_out=tuple(int(value) for value in baseline.get("transfers_out") or []),
            transfer_hits=int(baseline.get("transfer_hits") or 0),
            decision_mode=f"SHADOW_H1_MECHANICS_ON_PRODUCTION_SQUAD::{provider_id}",
            xi_excluded=exclusions,
        )
        result["variant"] = _variant(
            variant_id=f"h1_mechanics::{provider_id}",
            kind=kind,
            provider_id=provider_id,
            decision=decision,
            source_surface_hashes=task["source_surface_hashes"],
            note="Same production transfers/final 15; challenger H1 chooses XI, captain, vice and bench.",
        )
        return result
    if kind == "CHALLENGER_H1_AIRSENAL_H2_PLUS":
        surface = _hybrid_h1_then_airsenal(
            provider_id=provider_id,
            challenger=challenger,
            airsenal=surfaces["airsenal"],
            max_horizon=int(plan["max_horizon"]),
        )
        solved = _optimise_once(
            official=official,
            surface=surface,
            team=team,
            max_horizon=int(plan["max_horizon"]),
            exclusions=exclusions,
        )
        if solved.decision is None:
            result["status"] = "OPTIMISER_NO_DECISION"
            return result
        result["variant"] = _variant(
            variant_id=f"h1_plus_airsenal_future::{provider_id}",
            kind=kind,
            provider_id=provider_id,
            decision=solved.decision,
            source_surface_hashes=task["source_surface_hashes"],
            note="Challenger supplies H1; AIrsenal supplies H2+ planning horizons.",
        )
        return result
    if kind == "CHALLENGER_AVAILABILITY_ON_AIRSENAL_XP":
        overlay, fields = _availability_overlay(
            provider_id=provider_id,
            challenger=challenger,
            airsenal=surfaces["airsenal"],
            required_ids=decision_universe,
            max_horizon=int(plan["max_horizon"]),
        )
        if fields != task.get("overlay_fields"):
            raise TournamentContractError("availability overlay fields changed after plan")
        solved = _optimise_once(
            official=official,
            surface=overlay,
            team=team,
            max_horizon=int(plan["max_horizon"]),
            exclusions=exclusions,
        )
        if solved.decision is None:
            result["status"] = "OPTIMISER_NO_DECISION"
            return result
        result["variant"] = _variant(
            variant_id=f"availability_on_airsenal::{provider_id}",
            kind=kind,
            provider_id=provider_id,
            decision=solved.decision,
            source_surface_hashes=task["source_surface_hashes"],
            overlay_fields=fields,
            note="AIrsenal xP unchanged; complete challenger availability fields only.",
        )
        return result
    if kind == "PURE_PROVIDER_CONTIGUOUS_PLAN":
        provider_horizon = int(task["provider_horizon"])
        solved = _optimise_once(
            official=official,
            surface=challenger,
            team=team,
            max_horizon=provider_horizon,
            exclusions=exclusions,
        )
        if solved.decision is None:
            result["status"] = "OPTIMISER_NO_DECISION"
            return result
        result["variant"] = _variant(
            variant_id=f"pure_provider_plan::{provider_id}",
            kind=kind,
            provider_id=provider_id,
            decision=solved.decision,
            source_surface_hashes=task["source_surface_hashes"],
            note=f"Provider-only plan over genuine H1-H{provider_horizon} contiguous coverage.",
        )
        return result
    raise TournamentContractError("unreachable task kind")


def solve_task(*, season: str, control_plane_sha: str, candidate_tag: str, task_id: str) -> dict[str, Any]:
    public_store, private_store = _stores()
    public_releases = public_store.list_releases()
    private_releases = private_store.list_releases()
    candidate = _find_candidate_by_tag(public_releases, candidate_tag)
    with tempfile.TemporaryDirectory(prefix="apex-parallel-task-") as tmp:
        root = Path(tmp)
        readiness, manager_attempt, surfaces, hashes, public_files = _load_context(
            public_store=public_store,
            private_store=private_store,
            public_releases=public_releases,
            private_releases=private_releases,
            candidate_release=candidate,
            root=root,
        )
        plan = _derive_plan(
            readiness=readiness,
            private_attempt=manager_attempt,
            surfaces=surfaces,
            surface_hashes=hashes,
            public_files=public_files,
            control_plane_sha=control_plane_sha,
        )
        if plan["source"]["season"] != season:
            raise TournamentContractError("task season mismatch")
        task = next((row for row in plan["tasks"] if row["task_id"] == task_id), None)
        if task is None:
            raise TournamentContractError(f"task is not part of deterministic plan: {task_id}")
        deadline = _parse_utc(plan["source"]["deadline"])
        if _utc_now() >= deadline:
            raise TournamentContractError("new decision-lab task cannot start after deadline")
        fingerprint = _task_fingerprint(plan, task)
        tag = _task_release_tag(
            season=season,
            run_id=plan["source"]["run_id"],
            control_plane_sha=control_plane_sha,
            task_id=task_id,
        )
        prior = _find_release(private_releases, tag)
        if prior is not None:
            payload = _load_task_release(
                private_store=private_store,
                release=prior,
                expected_fingerprint=fingerprint,
                deadline=plan["source"]["deadline"],
                workdir=root / "existing",
            )
            return {"status": "REUSED", "tag": tag, "task": payload["task"]}
        result = _solve_task_from_context(
            plan=plan,
            task=task,
            private_attempt=manager_attempt,
            surfaces=surfaces,
            surface_hashes=hashes,
            public_files=public_files,
        )
        sealed_at = _utc_now()
        if sealed_at >= deadline:
            raise TournamentContractError("decision-lab task finished after deadline and will not be sealed")
        payload = {
            "schema_version": 1,
            "contract": TASK_CONTRACT,
            "exposure_class": "PRIVATE_MANAGER",
            "production_influence": "NONE",
            "serving_authorized": False,
            "promotion_authority": False,
            "automatic_serving_change": False,
            "frozen_engine_sha": FROZEN_APEX_SHA,
            "control_plane_sha": control_plane_sha,
            "source": plan["source"],
            "plan_sha256": plan["plan_sha256"],
            "task_fingerprint_sha256": fingerprint,
            "task": task,
            "sealed_at": sealed_at.astimezone(timezone.utc).isoformat(),
            "result": result,
        }
        _write_private_release(
            private_store=private_store,
            tag=tag,
            payload=payload,
            payload_name="decision_lab_task.json",
            attestation_name="decision_lab_task_attestation.json",
            scope=TASK_SCOPE,
            workdir=root / "publish",
            title=f"Apex V2 private decision-lab task {season} {plan['source']['run_id']} {task_id}",
        )
        return {"status": "SEALED", "tag": tag, "task": task}


def _matrix_key(kind: str) -> str:
    return {
        "H1_MECHANICS_ON_PRODUCTION_SQUAD": "h1_mechanics",
        "CHALLENGER_H1_AIRSENAL_H2_PLUS": "h1_plus_airsenal_future",
        "CHALLENGER_AVAILABILITY_ON_AIRSENAL_XP": "availability_on_airsenal",
        "PURE_PROVIDER_CONTIGUOUS_PLAN": "pure_provider_plan",
    }[kind]


def _assemble_one(
    *,
    private_store: Any,
    private_releases: list[dict[str, Any]],
    plan: dict[str, Any],
    private_attempt: dict[str, Any],
    surfaces: dict[str, dict[str, Any]],
    surface_hashes: dict[str, str],
    public_files: dict[str, Path],
    control_plane_sha: str,
    root: Path,
) -> dict[str, Any]:
    source = plan["source"]
    run_id = source["run_id"]
    lab_tag = f"{LAB_PREFIX}/{source['season']}/{run_id}"
    existing = _find_release(private_releases, lab_tag)
    if existing is not None:
        lab = _load_private_payload(
            store=private_store,
            release=existing,
            payload_name="decision_lab.json",
            attestation_name="decision_lab_attestation.json",
            expected_assets=LAB_ASSETS,
            scope="PRIVATE_PROSPECTIVE_DECISION_LAB",
            workdir=root / "existing-lab",
        )
        if str((lab.get("source") or {}).get("candidate_readiness_sha256") or "") != source["candidate_readiness_sha256"]:
            raise TournamentContractError("existing canonical lab is bound to different candidate evidence")
        return {"status": "EXISTING", "tag": lab_tag}
    private_by_tag = {
        str(row.get("tag_name") or ""): row for row in private_releases if not row.get("draft")
    }
    task_payloads: dict[str, dict[str, Any]] = {}
    for task in plan["tasks"]:
        tag = _task_release_tag(
            season=source["season"],
            run_id=run_id,
            control_plane_sha=control_plane_sha,
            task_id=task["task_id"],
        )
        release = private_by_tag.get(tag)
        if release is None:
            raise TournamentContractError(f"canonical lab assembly missing required staging task: {task['task_id']}")
        task_payloads[task["task_id"]] = _load_task_release(
            private_store=private_store,
            release=release,
            expected_fingerprint=_task_fingerprint(plan, task),
            deadline=source["deadline"],
            workdir=root / f"task-{task['task_id']}",
        )
    baseline_task = next(row for row in plan["tasks"] if row["kind"] == "BASELINE_REPRODUCTION")
    baseline_payload = task_payloads[baseline_task["task_id"]]
    if (baseline_payload.get("result") or {}).get("status") != "BASELINE_VERIFIED":
        raise TournamentContractError("canonical lab assembly lacks verified production baseline")
    baseline_raw = private_attempt.get("system_decision")
    if not isinstance(baseline_raw, dict):
        raise TournamentContractError("canonical lab assembly lacks production decision")
    variants: dict[str, dict[str, Any]] = {
        "production_baseline": _variant(
            variant_id="production_baseline",
            kind="PRODUCTION_BASELINE",
            provider_id="airsenal",
            decision=baseline_raw,
            source_surface_hashes={"airsenal": surface_hashes["airsenal"]},
            note="Exact immutable production decision; baseline reproduction was independently verified predeadline.",
        )
    }
    matrix = json.loads(json.dumps(plan["experiment_matrix"]))
    for task in plan["tasks"]:
        if task["kind"] == "BASELINE_REPRODUCTION":
            continue
        payload = task_payloads[task["task_id"]]
        result = payload.get("result") or {}
        provider_id = task["provider_id"]
        key = _matrix_key(task["kind"])
        status = str(result.get("status") or "")
        variant = result.get("variant")
        if status == "SEALED_PREDEADLINE":
            if not isinstance(variant, dict):
                raise TournamentContractError("sealed staging task has no variant")
            variants[str(variant["variant_id"])] = variant
            matrix[provider_id][key] = "SEALED_PREDEADLINE"
        elif status == "OPTIMISER_NO_DECISION":
            if variant is not None:
                raise TournamentContractError("no-decision task unexpectedly contains variant")
            matrix[provider_id][key] = "OPTIMISER_NO_DECISION"
        else:
            raise TournamentContractError(f"unexpected staging result status: {status}")
    if any(value == "PENDING_TASK" for row in matrix.values() for value in row.values()):
        raise TournamentContractError("canonical lab assembly left pending experiment state")
    canonical = private_attempt.get("canonical_forecast") or {}
    official = official_from_dict(canonical.get("official") or {})
    team = team_from_dict(private_attempt["team_state"])
    exclusions = _hard_exclusions_from_public_evidence(
        public_files, gameweek=int(source["target_gameweek"])
    )
    lab = {
        "schema_version": 1,
        "contract": LAB_CONTRACT,
        "exposure_class": "PRIVATE_MANAGER",
        "production_influence": "NONE",
        "serving_authorized": False,
        "promotion_authority": False,
        "automatic_serving_change": False,
        "sealed_before_outcomes": True,
        "decision_variants_sealed_predeadline": True,
        "assembly_may_follow_deadline": True,
        "postdeadline_backfill_forbidden": True,
        "parallel_staging_contract": TASK_CONTRACT,
        "parallel_plan_sha256": plan["plan_sha256"],
        "frozen_engine_sha": FROZEN_APEX_SHA,
        "control_plane_sha": control_plane_sha,
        "source": source,
        "policy": {
            "provider_neutral_variants": True,
            "dastan_prior_advantage": False,
            "h1_mechanics_isolates_lineup_captain_bench": True,
            "h1_plus_future_tests_transfer_and_mechanics_impact": True,
            "availability_overlay_requires_complete_preoutcome_field": True,
            "expected_points_never_rescaled_from_expected_minutes": True,
            "no_hindsight_imputation": True,
            "each_staging_task_uses_at_most_one_full_transfer_optimisation": True,
        },
        "decision_universe_player_count": plan["decision_universe_player_count"],
        "decision_universe_player_ids_published": False,
        "private_position_map": {str(player.element_id): player.position.value for player in official.players},
        "hard_exclusion_count": len(exclusions),
        "max_airsenal_planning_horizon": plan["max_horizon"],
        "team_context": {
            "active_chip": team.active_chip,
            "free_transfers": team.free_transfers,
            "bank_tenths": team.bank_tenths,
        },
        "baseline_variant_id": "production_baseline",
        "experiment_matrix": matrix,
        "variants": variants,
    }
    _write_private_release(
        private_store=private_store,
        tag=lab_tag,
        payload=lab,
        payload_name="decision_lab.json",
        attestation_name="decision_lab_attestation.json",
        scope="PRIVATE_PROSPECTIVE_DECISION_LAB",
        workdir=root / "publish-lab",
        title=f"Apex V2 private prospective decision lab {source['season']} GW{source['target_gameweek']} {run_id}",
    )
    return {"status": "ASSEMBLED", "tag": lab_tag, "variant_count": len(variants)}


def assemble(*, season: str, control_plane_sha: str) -> dict[str, Any]:
    public_store, private_store = _stores()
    public_releases = public_store.list_releases()
    private_releases = private_store.list_releases()
    outputs: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="apex-parallel-assemble-") as tmp:
        root = Path(tmp)
        for candidate in _candidate_releases(public_releases, season):
            readiness = _download_candidate(public_store, candidate, root / f"candidate-{candidate['id']}")
            if readiness.get("tournament_ready") is not True:
                continue
            seal = readiness.get("common_seal") or {}
            if seal.get("eligible_common_predeadline_candidate") is not True:
                continue
            run_id = str(seal.get("run_id") or "")
            existing_lab = _find_release(private_releases, f"{LAB_PREFIX}/{season}/{run_id}")
            if existing_lab is not None:
                outputs.append(
                    _assemble_one(
                        private_store=private_store,
                        private_releases=private_releases,
                        plan={
                            "source": {
                                "season": season,
                                "run_id": run_id,
                                "candidate_readiness_sha256": readiness["readiness_sha256"],
                            }
                        },
                        private_attempt={},
                        surfaces={},
                        surface_hashes={},
                        public_files={},
                        control_plane_sha=control_plane_sha,
                        root=root / f"existing-{run_id}",
                    )
                )
                continue
            readiness, manager_attempt, surfaces, hashes, public_files = _load_context(
                public_store=public_store,
                private_store=private_store,
                public_releases=public_releases,
                private_releases=private_releases,
                candidate_release=candidate,
                root=root / f"context-{run_id}",
            )
            plan = _derive_plan(
                readiness=readiness,
                private_attempt=manager_attempt,
                surfaces=surfaces,
                surface_hashes=hashes,
                public_files=public_files,
                control_plane_sha=control_plane_sha,
            )
            # Assemble only when every deterministic task for this control-plane version exists.
            expected_tags = [
                _task_release_tag(
                    season=season,
                    run_id=run_id,
                    control_plane_sha=control_plane_sha,
                    task_id=task["task_id"],
                )
                for task in plan["tasks"]
            ]
            private_tags = {str(row.get("tag_name") or "") for row in private_releases if not row.get("draft")}
            if not all(tag in private_tags for tag in expected_tags):
                continue
            outputs.append(
                _assemble_one(
                    private_store=private_store,
                    private_releases=private_releases,
                    plan=plan,
                    private_attempt=manager_attempt,
                    surfaces=surfaces,
                    surface_hashes=hashes,
                    public_files=public_files,
                    control_plane_sha=control_plane_sha,
                    root=root / f"assemble-{run_id}",
                )
            )
            private_releases = private_store.list_releases()
    return {
        "schema_version": 1,
        "contract": PARALLEL_CONTROLLER_CONTRACT,
        "mode": "ASSEMBLE",
        "production_influence": "NONE",
        "serving_authorized": False,
        "results": outputs,
    }


def postoutcome(*, season: str, control_plane_sha: str) -> dict[str, Any]:
    public_store, private_store = _stores()
    decision_quality = publish_completed_decision_quality(
        public_store=public_store,
        private_store=private_store,
        season=season,
        control_plane_sha=control_plane_sha,
    )
    edge = score_completed_labs(
        public_store=public_store, private_store=private_store, season=season
    )
    learning = publish_decision_edge_learning(private_store=private_store, season=season)
    return {
        "schema_version": 1,
        "contract": PARALLEL_CONTROLLER_CONTRACT,
        "mode": "POSTOUTCOME",
        "production_influence": "NONE",
        "serving_authorized": False,
        "decision_quality_published": decision_quality,
        "decision_edge": edge,
        "decision_edge_learning": {
            "through_observation": learning.get("through_observation"),
            "owner_review_queue": learning.get("owner_review_queue") or [],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("prepare", "solve-task", "assemble", "postoutcome"), required=True)
    parser.add_argument("--season", default="2026-2027")
    parser.add_argument("--control-plane-sha", required=True)
    parser.add_argument("--candidate-tag")
    parser.add_argument("--task-id")
    args = parser.parse_args()
    if args.mode == "prepare":
        result = prepare(season=args.season, control_plane_sha=args.control_plane_sha)
    elif args.mode == "solve-task":
        if not args.candidate_tag or not args.task_id:
            parser.error("--solve-task requires --candidate-tag and --task-id")
        result = solve_task(
            season=args.season,
            control_plane_sha=args.control_plane_sha,
            candidate_tag=args.candidate_tag,
            task_id=args.task_id,
        )
    elif args.mode == "assemble":
        result = assemble(season=args.season, control_plane_sha=args.control_plane_sha)
    else:
        result = postoutcome(season=args.season, control_plane_sha=args.control_plane_sha)
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
