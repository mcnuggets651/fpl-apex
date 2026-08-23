"""Versioned, provenance-bound FPL RuleSet for Apex V2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping
from urllib.parse import urlparse

from .canonical import canonical_sha256
from .ids import RuleSetId


JsonScalar = str | int | bool | None
JsonValue = JsonScalar | tuple["JsonValue", ...] | tuple[tuple[str, "JsonValue"], ...]
OFFICIAL_RULE_HOSTS = frozenset({"www.premierleague.com", "premierleague.com", "fantasy.premierleague.com"})
FPL_POSITIONS = frozenset({"GK", "DEF", "MID", "FWD"})


def _freeze(value: object) -> JsonValue:
    if isinstance(value, float):
        raise TypeError("RuleSet semantic values cannot contain floats")
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Mapping):
        return tuple(sorted((str(key), _freeze(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    raise TypeError(f"unsupported RuleSet semantic value: {type(value).__name__}")


def _thaw(value: JsonValue) -> object:
    if isinstance(value, tuple):
        if all(
            isinstance(item, tuple)
            and len(item) == 2
            and isinstance(item[0], str)
            for item in value
        ):
            return {key: _thaw(item) for key, item in value}
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class OfficialRuleSource:
    source_id: str
    publisher: str
    title: str
    url: str
    published_on: str
    verified_on: str

    def __post_init__(self) -> None:
        for field_name in (
            "source_id",
            "publisher",
            "title",
            "url",
            "published_on",
            "verified_on",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"OfficialRuleSource {field_name} cannot be empty")
        if self.publisher != "Premier League":
            raise ValueError("production RuleSet sources must be official Premier League sources")
        parsed = urlparse(self.url)
        if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_RULE_HOSTS:
            raise ValueError(
                "RuleSet source URL must be HTTPS on an approved Premier League/FPL host"
            )

    def as_dict(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "publisher": self.publisher,
            "title": self.title,
            "url": self.url,
            "published_on": self.published_on,
            "verified_on": self.verified_on,
        }


@dataclass(frozen=True, slots=True)
class RuleDefinition:
    rule_id: str
    capability: str
    value: JsonValue
    source_ids: tuple[str, ...]
    effective_season: str
    effective_from: str

    @classmethod
    def create(
        cls,
        *,
        rule_id: str,
        capability: str,
        value: object,
        source_ids: Iterable[str],
        effective_season: str,
        effective_from: str,
    ) -> "RuleDefinition":
        return cls(
            rule_id=str(rule_id).strip(),
            capability=str(capability).strip(),
            value=_freeze(value),
            source_ids=tuple(sorted(set(str(item).strip() for item in source_ids))),
            effective_season=str(effective_season).strip(),
            effective_from=str(effective_from).strip(),
        )

    def __post_init__(self) -> None:
        if not self.rule_id or not self.capability:
            raise ValueError("RuleDefinition rule_id/capability cannot be empty")
        if not self.source_ids or any(not item for item in self.source_ids):
            raise ValueError(f"{self.rule_id} requires at least one official source")
        if not self.effective_season or not self.effective_from:
            raise ValueError(f"{self.rule_id} requires effective season/date")

    def as_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "capability": self.capability,
            "value": _thaw(self.value),
            "source_ids": list(self.source_ids),
            "effective_season": self.effective_season,
            "effective_from": self.effective_from,
        }

    def thawed_value(self) -> object:
        return _thaw(self.value)


@dataclass(frozen=True, slots=True)
class RuleSet:
    season: str
    sources: tuple[OfficialRuleSource, ...]
    rules: tuple[RuleDefinition, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported RuleSet schema_version")
        if not self.season.strip():
            raise ValueError("RuleSet season cannot be empty")
        sources = tuple(sorted(self.sources, key=lambda row: row.source_id))
        rules = tuple(sorted(self.rules, key=lambda row: row.rule_id))
        source_ids = [row.source_id for row in sources]
        rule_ids = [row.rule_id for row in rules]
        if not sources or len(source_ids) != len(set(source_ids)):
            raise ValueError("RuleSet source IDs must be non-empty and unique")
        if not rules or len(rule_ids) != len(set(rule_ids)):
            raise ValueError("RuleSet rule IDs must be non-empty and unique")
        available = set(source_ids)
        for rule in rules:
            if rule.effective_season != self.season:
                raise ValueError(
                    f"{rule.rule_id} season {rule.effective_season} != RuleSet {self.season}"
                )
            unknown = sorted(set(rule.source_ids) - available)
            if unknown:
                raise ValueError(f"{rule.rule_id} references unknown sources: {unknown}")
        object.__setattr__(self, "sources", sources)
        object.__setattr__(self, "rules", rules)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-fpl-ruleset",
            "schema_version": self.schema_version,
            "season": self.season,
            "sources": [source.as_dict() for source in self.sources],
            "rules": [rule.as_dict() for rule in self.rules],
        }

    @property
    def ruleset_id(self) -> RuleSetId:
        return RuleSetId(canonical_sha256(self.semantic_payload()))

    def require(self, rule_id: str) -> RuleDefinition:
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        raise KeyError(f"RuleSet has no rule {rule_id!r}")

    def value(self, rule_id: str) -> object:
        return self.require(rule_id).thawed_value()

    def integer(self, rule_id: str) -> int:
        value = self.value(rule_id)
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"Rule {rule_id} is not an integer")
        return value

    def mapping(self, rule_id: str) -> dict[str, object]:
        value = self.value(rule_id)
        if not isinstance(value, dict):
            raise TypeError(f"Rule {rule_id} is not a mapping")
        return value

    def validate_squad(
        self,
        *,
        positions: Iterable[str],
        club_ids: Iterable[int],
        prices_tenths: Iterable[int],
    ) -> tuple[str, ...]:
        positions = tuple(positions)
        clubs = tuple(club_ids)
        prices = tuple(prices_tenths)
        errors: list[str] = []
        squad_size = self.integer("FPL-SQUAD-SIZE-001")
        if not (len(positions) == len(clubs) == len(prices) == squad_size):
            errors.append(f"squad must contain exactly {squad_size} players")
            return tuple(errors)
        unknown_positions = sorted(set(positions) - FPL_POSITIONS)
        if unknown_positions:
            errors.append(f"squad contains unknown positions: {unknown_positions}")
        expected = self.mapping("FPL-SQUAD-POSITIONS-001")
        for position, count in expected.items():
            actual = sum(item == position for item in positions)
            if actual != int(count):
                errors.append(f"squad {position} count {actual} != {count}")
        if any(isinstance(club, bool) or not isinstance(club, int) or club <= 0 for club in clubs):
            errors.append("all squad club IDs must be positive integers")
        else:
            max_club = self.integer("FPL-SQUAD-MAX-CLUB-001")
            for club in set(clubs):
                actual = sum(item == club for item in clubs)
                if actual > max_club:
                    errors.append(f"club {club} has {actual} players; max is {max_club}")
        if any(
            isinstance(price, bool) or not isinstance(price, int) or price <= 0
            for price in prices
        ):
            errors.append("all squad prices must be positive integer tenths")
        elif sum(prices) > self.integer("FPL-SQUAD-BUDGET-TENTHS-001"):
            errors.append("squad exceeds official budget")
        return tuple(errors)

    def validate_lineup(self, *, positions: Iterable[str]) -> tuple[str, ...]:
        positions = tuple(positions)
        errors: list[str] = []
        xi_size = self.integer("FPL-XI-SIZE-001")
        if len(positions) != xi_size:
            errors.append(f"lineup must contain exactly {xi_size} players")
            return tuple(errors)
        unknown_positions = sorted(set(positions) - FPL_POSITIONS)
        if unknown_positions:
            errors.append(f"lineup contains unknown positions: {unknown_positions}")
        minimums = self.mapping("FPL-XI-POSITION-MIN-001")
        maximums = self.mapping("FPL-XI-POSITION-MAX-001")
        for position in ("GK", "DEF", "MID", "FWD"):
            actual = sum(item == position for item in positions)
            minimum = int(minimums[position])
            maximum = int(maximums[position])
            if actual < minimum or actual > maximum:
                errors.append(
                    f"lineup {position} count {actual} outside [{minimum}, {maximum}]"
                )
        return tuple(errors)
