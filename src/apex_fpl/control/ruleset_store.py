"""Immutable self-addressing storage for exact V2 FPL RuleSet semantics."""

from __future__ import annotations

import json

from apex_fpl.control.artifact_store import ArtifactIntegrityError, ArtifactStore
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.ids import RuleSetId
from apex_fpl.core.rules import OfficialRuleSource, RuleDefinition, RuleSet


def _int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be exact integer")
    return value


def _text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty string")
    return value.strip()


def _objects(value: object, *, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"{label} must be an array of objects")
    return [dict(row) for row in value]


def _strings(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(row, str) for row in value):
        raise ValueError(f"{label} must be an array of strings")
    return tuple(value)


def store_ruleset(ruleset: RuleSet, *, store: ArtifactStore) -> str:
    ref = store.put_bytes(
        canonical_json_bytes(ruleset.semantic_payload()),
        media_type="application/json",
        schema_name="apex-fpl-ruleset",
        schema_version=str(ruleset.schema_version),
    )
    if ref.artifact_id != str(ruleset.ruleset_id):
        raise ValueError("RuleSet storage identity mismatch")
    return ref.artifact_id


def load_ruleset_artifact(
    ruleset_id: RuleSetId | str,
    *,
    store: ArtifactStore,
) -> RuleSet:
    expected = RuleSetId(str(ruleset_id))
    try:
        content = store.read_bytes(str(expected))
    except (FileNotFoundError, ArtifactIntegrityError) as exc:
        raise ValueError("RuleSet artifact failed integrity verification") from exc
    try:
        raw = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("RuleSet artifact is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict) or raw.get("schema_name") != "apex-fpl-ruleset":
        raise ValueError("not an Apex FPL RuleSet artifact")
    if canonical_json_bytes(raw) != content:
        raise ValueError("RuleSet artifact is not canonical JSON")
    sources = tuple(
        OfficialRuleSource(
            source_id=_text(row.get("source_id"), label="RuleSet source_id"),
            publisher=_text(row.get("publisher"), label="RuleSet publisher"),
            title=_text(row.get("title"), label="RuleSet source title"),
            url=_text(row.get("url"), label="RuleSet source URL"),
            published_on=_text(row.get("published_on"), label="RuleSet source published_on"),
            verified_on=_text(row.get("verified_on"), label="RuleSet source verified_on"),
        )
        for row in _objects(raw.get("sources"), label="RuleSet sources")
    )
    rules = tuple(
        RuleDefinition.create(
            rule_id=_text(row.get("rule_id"), label="RuleSet rule_id"),
            capability=_text(row.get("capability"), label="RuleSet capability"),
            value=row.get("value"),
            source_ids=_strings(row.get("source_ids"), label="RuleSet source_ids"),
            effective_season=_text(
                row.get("effective_season"), label="RuleSet effective_season"
            ),
            effective_from=_text(row.get("effective_from"), label="RuleSet effective_from"),
        )
        for row in _objects(raw.get("rules"), label="RuleSet rules")
    )
    ruleset = RuleSet(
        season=_text(raw.get("season"), label="RuleSet season"),
        sources=sources,
        rules=rules,
        schema_version=_int(raw.get("schema_version"), label="RuleSet schema_version"),
    )
    if ruleset.ruleset_id != expected:
        raise ValueError("RuleSet semantic identity mismatch")
    return ruleset
