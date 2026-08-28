"""Persist and independently replay the Apex V2 production authority root."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json

from apex_fpl.control.artifact_store import ArtifactIntegrityError, ArtifactStore
from apex_fpl.control.champion_authority import load_production_champion_generation
from apex_fpl.control.learning_policy_registry import load_learning_policy_registry_bytes
from apex_fpl.control.outcome_truth_registry import load_outcome_truth_registry_bytes
from apex_fpl.control.provenance_replay import load_build_manifest
from apex_fpl.control.ruleset_store import load_ruleset_artifact
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.production_authority_root import ProductionAuthorityRoot


@dataclass(frozen=True, slots=True)
class VerifiedProductionAuthorityRoot:
    root: ProductionAuthorityRoot
    artifact_id: str


def _strict_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be integer")
    return value


def _optional_text(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty string or null")
    return value.strip()


def _instant(value: str, *, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed


def store_production_authority_root(
    root: ProductionAuthorityRoot,
    *,
    store: ArtifactStore,
) -> str:
    """Store one root as its canonical semantic payload."""

    ref = store.put_bytes(
        canonical_json_bytes(root.semantic_payload()),
        media_type="application/json",
        schema_name="apex-production-authority-root",
        schema_version="1",
    )
    if ref.artifact_id != root.root_id:
        raise ValueError("production authority root storage identity mismatch")
    return ref.artifact_id


def load_production_authority_root(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> ProductionAuthorityRoot:
    """Replay one root contract and prove its self-addressed identity."""

    try:
        content = store.read_bytes(artifact_id)
    except (FileNotFoundError, ArtifactIntegrityError) as exc:
        raise ValueError("production authority root failed integrity verification") from exc
    try:
        raw = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("production authority root is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError("production authority root must be object")
    if canonical_json_bytes(raw) != content:
        raise ValueError("production authority root must be canonical JSON")
    if raw.get("schema_name") != "apex-production-authority-root":
        raise ValueError("not an Apex production authority root")
    if _strict_int(raw.get("schema_version"), label="authority root schema_version") != 1:
        raise ValueError("unsupported production authority root schema")
    root = ProductionAuthorityRoot(
        season=str(raw.get("season") or ""),
        generation=_strict_int(raw.get("generation"), label="authority root generation"),
        parent_root_artifact_id=_optional_text(
            raw.get("parent_root_artifact_id"),
            label="authority root parent_root_artifact_id",
        ),
        champion_generation_artifact_id=str(raw.get("champion_generation_artifact_id") or ""),
        ruleset_artifact_id=str(raw.get("ruleset_artifact_id") or ""),
        ruleset_id=str(raw.get("ruleset_id") or ""),
        learning_policy_registry_artifact_id=str(
            raw.get("learning_policy_registry_artifact_id") or ""
        ),
        learning_policy_id=str(raw.get("learning_policy_id") or ""),
        outcome_truth_registry_artifact_id=str(
            raw.get("outcome_truth_registry_artifact_id") or ""
        ),
        outcome_truth_registry_id=str(raw.get("outcome_truth_registry_id") or ""),
        build_manifest_artifact_id=str(raw.get("build_manifest_artifact_id") or ""),
        build_manifest_id=str(raw.get("build_manifest_id") or ""),
        change_control_artifact_id=str(raw.get("change_control_artifact_id") or ""),
        authorized_by=str(raw.get("authorized_by") or ""),
        authorized_at=str(raw.get("authorized_at") or ""),
        valid_from=str(raw.get("valid_from") or ""),
        valid_until=str(raw.get("valid_until") or ""),
        reason=str(raw.get("reason") or ""),
        schema_version=1,
    )
    if root.semantic_payload() != raw or root.root_id != artifact_id:
        raise ValueError("production authority root semantic identity mismatch")
    return root


def verify_production_authority_root(
    artifact_id: str,
    *,
    as_of: str,
    store: ArtifactStore,
    expected_runtime_digest: str | None = None,
) -> VerifiedProductionAuthorityRoot:
    """Re-prove every long-lived authority bound by one root at the caller's ``as_of``."""

    root = load_production_authority_root(artifact_id, store=store)
    root.require_valid_at(as_of)
    replay_at = _instant(as_of, label="production authority root as_of")
    if replay_at < _instant(root.authorized_at, label="production authority root authorized_at"):
        raise ValueError("production authority root did not exist at replay as_of")
    if not store.verify(root.change_control_artifact_id):
        raise ValueError("production authority root change-control evidence is missing/corrupt")

    if root.parent_root_artifact_id is not None:
        parent = load_production_authority_root(root.parent_root_artifact_id, store=store)
        if parent.season != root.season or parent.generation + 1 != root.generation:
            raise ValueError("production authority root parent lineage is not contiguous")
        if _instant(parent.authorized_at, label="parent root authorized_at") > _instant(
            root.authorized_at,
            label="production authority root authorized_at",
        ):
            raise ValueError("production authority root predates its parent")

    champion = load_production_champion_generation(
        root.champion_generation_artifact_id,
        as_of=as_of,
        store=store,
    ).generation
    if champion.season != root.season:
        raise ValueError("production champion generation season does not match authority root")

    ruleset = load_ruleset_artifact(root.ruleset_artifact_id, store=store)
    if str(ruleset.ruleset_id) != root.ruleset_id:
        raise ValueError("RuleSet semantic identity does not match authority root")
    if ruleset.season != root.season:
        raise ValueError("RuleSet season does not match authority root")

    learning_registry = load_learning_policy_registry_bytes(
        store.read_bytes(root.learning_policy_registry_artifact_id)
    )
    if learning_registry.season != root.season:
        raise ValueError("learning-policy registry season does not match authority root")
    champion_policy = learning_registry.champion()
    if champion_policy is None or str(champion_policy.policy_id) != root.learning_policy_id:
        raise ValueError("learning-policy champion does not match authority root")
    learning_registry.verify_policy(
        champion_policy,
        store=store,
        season=root.season,
        cutoff=as_of,
        production=True,
    )

    truth_registry = load_outcome_truth_registry_bytes(
        store.read_bytes(root.outcome_truth_registry_artifact_id)
    )
    if truth_registry.registry_id != root.outcome_truth_registry_id:
        raise ValueError("outcome-truth registry identity does not match authority root")

    build_manifest = load_build_manifest(
        root.build_manifest_artifact_id,
        store=store,
        expected_runtime_digest=expected_runtime_digest,
        verify_members=True,
    )
    if build_manifest.build_manifest_id != root.build_manifest_id:
        raise ValueError("build-manifest semantic identity does not match authority root")

    return VerifiedProductionAuthorityRoot(root=root, artifact_id=artifact_id)
