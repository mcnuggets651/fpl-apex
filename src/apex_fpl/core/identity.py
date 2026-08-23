"""Current-season player identity and reviewed cross-season linkage for Apex V2.

Names are display witnesses only. They are never sufficient to attach decision-critical
data to a current FPL player. Current Official FPL integer IDs are canonical for the
active season; ``PersonId`` exists only for reviewed cross-season linkage.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping

from .ids import PersonId


POSITION_BY_ELEMENT_TYPE = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


class IdentityIntegrityError(ValueError):
    """Raised when player identity cannot be used safely."""


@dataclass(frozen=True, slots=True, order=True)
class OfficialPlayerId:
    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int) or self.value <= 0:
            raise IdentityIntegrityError("Official FPL player ID must be a positive integer")

    def __int__(self) -> int:
        return self.value

    def __str__(self) -> str:
        return str(self.value)


class IdentityResolutionState(str, Enum):
    EXACT = "EXACT"
    CORROBORATED = "CORROBORATED"
    AMBIGUOUS = "AMBIGUOUS"
    UNMAPPED = "UNMAPPED"


@dataclass(frozen=True, slots=True)
class OfficialPlayerIdentity:
    player_id: OfficialPlayerId
    team_id: int
    position: str
    price_tenths: int
    display_name: str
    person_id: PersonId | None = None

    def __post_init__(self) -> None:
        if isinstance(self.team_id, bool) or not isinstance(self.team_id, int) or self.team_id <= 0:
            raise IdentityIntegrityError("Official player team_id must be a positive integer")
        if self.position not in {"GK", "DEF", "MID", "FWD"}:
            raise IdentityIntegrityError(f"invalid Official FPL position: {self.position!r}")
        if isinstance(self.price_tenths, bool) or not isinstance(self.price_tenths, int):
            raise IdentityIntegrityError("Official player price_tenths must be an integer")
        if self.price_tenths <= 0:
            raise IdentityIntegrityError("Official player price_tenths must be positive")
        if not self.display_name.strip():
            raise IdentityIntegrityError("Official player display_name cannot be empty")


@dataclass(frozen=True, slots=True)
class PersonLink:
    """Reviewed cross-season link. It must never be inferred from a name alone."""

    person_id: PersonId
    player_id: OfficialPlayerId
    source_reference: str

    def __post_init__(self) -> None:
        if not self.source_reference.strip():
            raise IdentityIntegrityError("PersonLink requires a reviewed source reference")


@dataclass(frozen=True, slots=True)
class IdentityWitness:
    """Identity facts supplied by an external dataset/evidence item.

    ``display_name`` is retained for audit output but is intentionally excluded from
    resolution logic. A stable Official ID or reviewed ``PersonId`` is required.
    """

    source: str
    claimed_player_id: OfficialPlayerId | None = None
    person_id: PersonId | None = None
    team_id: int | None = None
    position: str | None = None
    display_name: str | None = None


@dataclass(frozen=True, slots=True)
class IdentityResolution:
    state: IdentityResolutionState
    player: OfficialPlayerIdentity | None
    reasons: tuple[str, ...]
    source: str

    @property
    def decision_safe(self) -> bool:
        return self.state in {
            IdentityResolutionState.EXACT,
            IdentityResolutionState.CORROBORATED,
        }

    def require_decision_safe(self) -> OfficialPlayerIdentity:
        if not self.decision_safe or self.player is None:
            detail = "; ".join(self.reasons) or self.state.value
            raise IdentityIntegrityError(
                f"decision-critical identity is {self.state.value}: {detail}"
            )
        return self.player


class IdentityRegistry:
    """Immutable current-season Official FPL identity registry."""

    def __init__(
        self,
        players: Iterable[OfficialPlayerIdentity],
        *,
        person_links: Iterable[PersonLink] = (),
    ):
        by_id: dict[OfficialPlayerId, OfficialPlayerIdentity] = {}
        for player in players:
            if player.player_id in by_id:
                raise IdentityIntegrityError(
                    f"duplicate Official FPL player ID: {player.player_id}"
                )
            by_id[player.player_id] = player
        if not by_id:
            raise IdentityIntegrityError("Official identity registry cannot be empty")

        by_person: dict[PersonId, OfficialPlayerId] = {}
        for link in person_links:
            if link.player_id not in by_id:
                raise IdentityIntegrityError(
                    f"PersonLink targets unknown Official FPL player ID: {link.player_id}"
                )
            existing = by_person.get(link.person_id)
            if existing is not None and existing != link.player_id:
                raise IdentityIntegrityError(
                    f"PersonId {link.person_id} maps to multiple current Official IDs"
                )
            by_person[link.person_id] = link.player_id
        self._by_id = by_id
        self._by_person = by_person

    @classmethod
    def from_official_bootstrap(
        cls,
        bootstrap: Mapping[str, object],
        *,
        person_links: Iterable[PersonLink] = (),
    ) -> "IdentityRegistry":
        raw_players = bootstrap.get("elements")
        if not isinstance(raw_players, list) or not raw_players:
            raise IdentityIntegrityError("Official bootstrap has no player identities")
        players: list[OfficialPlayerIdentity] = []
        for row in raw_players:
            if not isinstance(row, Mapping):
                raise IdentityIntegrityError("Official bootstrap player row is not an object")
            raw_id = row.get("id")
            raw_team = row.get("team")
            raw_element_type = row.get("element_type")
            raw_cost = row.get("now_cost")
            for label, value in (
                ("id", raw_id),
                ("team", raw_team),
                ("element_type", raw_element_type),
                ("now_cost", raw_cost),
            ):
                if isinstance(value, bool) or not isinstance(value, int):
                    raise IdentityIntegrityError(
                        f"Official bootstrap {label} must be an exact integer: {value!r}"
                    )
            try:
                position = POSITION_BY_ELEMENT_TYPE[raw_element_type]
            except KeyError as exc:
                raise IdentityIntegrityError(
                    f"Official bootstrap has invalid element_type={raw_element_type}"
                ) from exc
            display_name = str(
                row.get("web_name")
                or row.get("second_name")
                or row.get("first_name")
                or ""
            ).strip()
            players.append(
                OfficialPlayerIdentity(
                    player_id=OfficialPlayerId(raw_id),
                    team_id=raw_team,
                    position=position,
                    price_tenths=raw_cost,
                    display_name=display_name,
                )
            )
        return cls(players, person_links=person_links)

    def get(self, player_id: OfficialPlayerId) -> OfficialPlayerIdentity | None:
        return self._by_id.get(player_id)

    def resolve(self, witness: IdentityWitness) -> IdentityResolution:
        reasons: list[str] = []
        by_claim = (
            self._by_id.get(witness.claimed_player_id)
            if witness.claimed_player_id is not None
            else None
        )
        linked_id = self._by_person.get(witness.person_id) if witness.person_id else None
        by_person = self._by_id.get(linked_id) if linked_id is not None else None

        if witness.claimed_player_id is not None and by_claim is None:
            reasons.append(
                f"claimed Official FPL player ID {witness.claimed_player_id} is unknown"
            )
        if witness.person_id is not None and by_person is None:
            reasons.append(f"PersonId {witness.person_id} has no reviewed current-season link")
        if by_claim is not None and by_person is not None and by_claim.player_id != by_person.player_id:
            return IdentityResolution(
                state=IdentityResolutionState.AMBIGUOUS,
                player=None,
                reasons=(
                    "explicit Official FPL ID conflicts with reviewed PersonId link",
                ),
                source=witness.source,
            )

        candidate = by_claim or by_person
        if candidate is None:
            # display_name is intentionally not consulted here.
            return IdentityResolution(
                state=IdentityResolutionState.UNMAPPED,
                player=None,
                reasons=tuple(reasons or ["no stable Official ID or reviewed PersonId link"]),
                source=witness.source,
            )

        if witness.team_id is not None and witness.team_id != candidate.team_id:
            reasons.append(
                f"team conflict source={witness.team_id} official={candidate.team_id}"
            )
        if witness.position is not None and witness.position != candidate.position:
            reasons.append(
                f"position conflict source={witness.position!r} official={candidate.position!r}"
            )
        if reasons:
            return IdentityResolution(
                state=IdentityResolutionState.AMBIGUOUS,
                player=None,
                reasons=tuple(reasons),
                source=witness.source,
            )

        state = (
            IdentityResolutionState.EXACT
            if by_claim is not None
            else IdentityResolutionState.CORROBORATED
        )
        return IdentityResolution(
            state=state,
            player=candidate,
            reasons=(),
            source=witness.source,
        )
