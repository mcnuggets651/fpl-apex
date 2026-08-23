"""Load reviewed RuleSet manifests outside the dependency-free constitutional core."""

from __future__ import annotations

from pathlib import Path

import yaml

from apex_fpl.core.rules import OfficialRuleSource, RuleDefinition, RuleSet


def load_ruleset(path: str | Path) -> RuleSet:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or int(raw.get("schema_version", -1)) != 1:
        raise ValueError("unsupported RuleSet manifest schema")
    season = str(raw.get("season") or "").strip()
    source_rows = raw.get("sources")
    rule_rows = raw.get("rules")
    if not isinstance(source_rows, list) or not isinstance(rule_rows, list):
        raise ValueError("RuleSet manifest requires source and rule lists")
    sources = tuple(
        OfficialRuleSource(
            source_id=str(row["source_id"]),
            publisher=str(row["publisher"]),
            title=str(row["title"]),
            url=str(row["url"]),
            published_on=str(row["published_on"]),
            verified_on=str(row["verified_on"]),
        )
        for row in source_rows
    )
    rules = tuple(
        RuleDefinition.create(
            rule_id=str(row["rule_id"]),
            capability=str(row["capability"]),
            value=row["value"],
            source_ids=row["source_ids"],
            effective_season=str(row["effective_season"]),
            effective_from=str(row["effective_from"]),
        )
        for row in rule_rows
    )
    return RuleSet(season=season, sources=sources, rules=rules)
