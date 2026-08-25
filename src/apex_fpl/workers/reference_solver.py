"""Isolated exact reference solver for the declared V2 tactical decision surface.

This module intentionally does not import the Apex DecisionEngine, decision mechanics,
optimisation package, services, or reference-mechanics checker. It consumes only the
sealed data-only reference-solver request contract and independently reconstructs the
declared current-Gameweek action surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations, permutations, product
from typing import Iterable

from apex_fpl.core.canonical import canonical_json_bytes, canonical_sha256
from apex_fpl.core.reference_solver_io import (
    ExactSolverValue,
    ReferenceSolverRequest,
    ReferenceSolverRun,
    ReferenceSolverRunStatus,
)


_POSITIONS = ("GK", "DEF", "MID", "FWD")
_OUTFIELD = ("DEF", "MID", "FWD")
_CHIP_RANK = {
    "NONE": 4,
    "TRIPLE_CAPTAIN": 3,
    "BENCH_BOOST": 2,
    "WILDCARD": 1,
    "FREE_HIT": 0,
}


class _SearchLimit(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _Player:
    player_id: int
    team_id: int
    position: str
    price: int


@dataclass(frozen=True, slots=True)
class _Owned:
    player_id: int
    team_id: int
    position: str
    current_price: int
    selling_price: int


@dataclass(frozen=True, slots=True)
class _Value:
    expected_points: Fraction
    appearance_probability: Fraction


@dataclass(frozen=True, slots=True)
class _SquadAction:
    chip: str
    transfers: tuple[tuple[int, int], ...]
    squad: tuple[_Player, ...]
    bank_after: int
    hit_points: int


@dataclass(frozen=True, slots=True)
class _Submission:
    xi_ids: tuple[int, ...]
    captain_id: int
    vice_id: int
    bench_gk_id: int
    bench_order: tuple[int, ...]
    xi_points: Fraction
    autosub_points: Fraction
    captain_bonus: Fraction
    squad_points_if_bench_boost: Fraction
    points_before_hits: Fraction
    objective: Fraction


@dataclass(slots=True)
class _Budget:
    limit: int
    nodes: int = 0

    def consume(self, count: int = 1) -> None:
        self.nodes += count
        if self.nodes > self.limit:
            raise _SearchLimit(f"search-node limit {self.limit} exceeded")


def _as_int(value: object, *, label: str, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be integer")
    if positive and value <= 0:
        raise ValueError(f"{label} must be positive")
    return value


def _rules(payload: dict[str, object]) -> dict[str, object]:
    rows = payload.get("rules")
    if not isinstance(rows, list):
        raise ValueError("RuleSet rules must be list")
    result: dict[str, object] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("RuleSet rule row must be object")
        rule_id = str(row.get("rule_id") or "")
        if not rule_id or rule_id in result:
            raise ValueError("RuleSet contains invalid/duplicate rule id")
        result[rule_id] = row.get("value")
    return result


def _rule_int(rules: dict[str, object], rule_id: str) -> int:
    if rule_id not in rules:
        raise ValueError(f"missing RuleSet rule {rule_id}")
    return _as_int(rules[rule_id], label=rule_id)


def _rule_map(rules: dict[str, object], rule_id: str) -> dict[str, object]:
    value = rules.get(rule_id)
    if not isinstance(value, dict):
        raise ValueError(f"RuleSet rule {rule_id} must be object")
    return value


def _parse_players(payload: dict[str, object]) -> tuple[_Player, ...]:
    rows = payload.get("players")
    if not isinstance(rows, list):
        raise ValueError("CandidateUniverse players must be list")
    result: list[_Player] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("candidate player must be object")
        position = str(row.get("position") or "")
        if position not in _POSITIONS:
            raise ValueError("candidate player position invalid")
        result.append(
            _Player(
                player_id=_as_int(row.get("player_id"), label="candidate player_id", positive=True),
                team_id=_as_int(row.get("team_id"), label="candidate team_id", positive=True),
                position=position,
                price=_as_int(
                    row.get("current_price_tenths"),
                    label="candidate current_price_tenths",
                    positive=True,
                ),
            )
        )
    result.sort(key=lambda row: row.player_id)
    if len({row.player_id for row in result}) != len(result):
        raise ValueError("CandidateUniverse contains duplicate player ids")
    return tuple(result)


def _parse_owned(payload: dict[str, object]) -> tuple[_Owned, ...]:
    rows = payload.get("squad")
    if not isinstance(rows, list) or len(rows) != 15:
        raise ValueError("ManagerState squad must contain 15 players")
    result: list[_Owned] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("owned player must be object")
        position = str(row.get("position") or "")
        if position not in _POSITIONS:
            raise ValueError("owned player position invalid")
        result.append(
            _Owned(
                player_id=_as_int(row.get("player_id"), label="owned player_id", positive=True),
                team_id=_as_int(row.get("team_id"), label="owned team_id", positive=True),
                position=position,
                current_price=_as_int(
                    row.get("current_price_tenths"),
                    label="owned current price",
                    positive=True,
                ),
                selling_price=_as_int(
                    row.get("selling_price_tenths"),
                    label="owned selling price",
                    positive=True,
                ),
            )
        )
    result.sort(key=lambda row: row.player_id)
    if len({row.player_id for row in result}) != 15:
        raise ValueError("ManagerState squad ids must be unique")
    return tuple(result)


def _validate_owned_matches(
    owned: tuple[_Owned, ...],
    players: tuple[_Player, ...],
) -> None:
    by_id = {row.player_id: row for row in players}
    errors: list[str] = []
    for row in owned:
        player = by_id.get(row.player_id)
        if player is None:
            errors.append(f"owned player {row.player_id} absent from CandidateUniverse")
            continue
        if (
            player.team_id != row.team_id
            or player.position != row.position
            or player.price != row.current_price
        ):
            errors.append(f"owned player {row.player_id} identity/price mismatch")
    if errors:
        raise ValueError("; ".join(errors))


def _build_values(
    forecast: dict[str, object],
    *,
    gameweek: int,
    player_ids: Iterable[int],
) -> dict[int, _Value]:
    requested = tuple(sorted(set(player_ids)))
    abstentions = forecast.get("abstentions")
    if not isinstance(abstentions, list):
        raise ValueError("Forecast abstentions must be list")
    bad: set[int] = set()
    for row in abstentions:
        if not isinstance(row, dict):
            raise ValueError("Forecast abstention row must be object")
        target = row.get("target")
        if not isinstance(target, dict):
            raise ValueError("Forecast abstention target must be object")
        if target.get("gameweek") == gameweek:
            player_id = _as_int(target.get("player_id"), label="abstention player_id", positive=True)
            if player_id in requested:
                bad.add(player_id)
    if bad:
        raise ValueError(
            "reference solver cannot neutral-fill forecast abstentions: "
            + ",".join(str(item) for item in sorted(bad))
        )

    rows = forecast.get("rows")
    if not isinstance(rows, list):
        raise ValueError("Forecast rows must be list")
    expected = {player_id: Fraction(0, 1) for player_id in requested}
    no_appearance = {player_id: Fraction(1, 1) for player_id in requested}
    seen = {player_id: False for player_id in requested}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Forecast row must be object")
        target = row.get("target")
        if not isinstance(target, dict) or target.get("gameweek") != gameweek:
            continue
        player_id = _as_int(target.get("player_id"), label="Forecast player_id", positive=True)
        if player_id not in expected:
            continue
        point_support = row.get("points_distribution")
        minute_support = row.get("minutes_distribution")
        if not isinstance(point_support, list) or not isinstance(minute_support, list):
            raise ValueError("Forecast distributions must be lists")
        point_total = 0
        point_mass = 0
        for item in point_support:
            if not isinstance(item, list) or len(item) != 2:
                raise ValueError("points_distribution support row invalid")
            value = _as_int(item[0], label="forecast point support value")
            probability = _as_int(
                item[1],
                label="forecast point support probability",
                positive=True,
            )
            point_mass += probability
            point_total += value * probability
        if point_mass != 10_000:
            raise ValueError("points distribution mass must equal 10000")
        p_zero = 0
        mass = 0
        for item in minute_support:
            if not isinstance(item, list) or len(item) != 2:
                raise ValueError("minutes_distribution support row invalid")
            value = _as_int(item[0], label="forecast minute support value")
            probability = _as_int(
                item[1],
                label="forecast minute support probability",
                positive=True,
            )
            mass += probability
            if value == 0:
                p_zero += probability
        if mass != 10_000:
            raise ValueError("minutes distribution mass must equal 10000")
        expected[player_id] += Fraction(point_total, 10_000)
        no_appearance[player_id] *= Fraction(p_zero, 10_000)
        seen[player_id] = True
    return {
        player_id: _Value(
            expected_points=expected[player_id],
            appearance_probability=(
                Fraction(0, 1) if not seen[player_id] else 1 - no_appearance[player_id]
            ),
        )
        for player_id in requested
    }


def _available_chips(
    state: dict[str, object],
    rules: dict[str, object],
) -> set[str]:
    gameweek = _as_int(state.get("gameweek"), label="manager gameweek", positive=True)
    first_last = _rule_int(rules, "FPL-CHIP-FIRST-SET-LAST-GW-001")
    second_first = _rule_int(rules, "FPL-CHIP-SECOND-SET-FIRST-GW-001")
    if gameweek <= first_last:
        set_number = 1
    elif gameweek >= second_first:
        set_number = 2
    else:
        raise ValueError("gameweek lies outside configured chip sets")

    chips_used = state.get("chips_used")
    if not isinstance(chips_used, list):
        raise ValueError("ManagerState chips_used must be list")
    used: set[tuple[str, int]] = set()
    for row in chips_used:
        if not isinstance(row, dict):
            raise ValueError("chip ledger row must be object")
        used.add(
            (
                str(row.get("chip") or ""),
                _as_int(row.get("set_number"), label="chip set_number", positive=True),
            )
        )
    available = {"NONE"}
    for chip in ("TRIPLE_CAPTAIN", "BENCH_BOOST", "WILDCARD", "FREE_HIT"):
        if (chip, set_number) not in used:
            available.add(chip)

    free_hit_disallowed = rules.get("FPL-FREE-HIT-DISALLOWED-GWS-001")
    wildcard_disallowed = rules.get("FPL-WILDCARD-DISALLOWED-GWS-001")
    if isinstance(free_hit_disallowed, list) and gameweek in free_hit_disallowed:
        available.discard("FREE_HIT")
    if isinstance(wildcard_disallowed, list) and gameweek in wildcard_disallowed:
        available.discard("WILDCARD")
    boundary = _rule_map(rules, "FPL-FREE-HIT-CROSS-HALF-CONSECUTIVE-001")
    if boundary.get("allowed") is False and gameweek == int(boundary["second_half_gw"]):
        first = int(boundary["first_half_gw"])
        if any(
            isinstance(row, dict)
            and row.get("chip") == "FREE_HIT"
            and row.get("gameweek") == first
            for row in chips_used
        ):
            available.discard("FREE_HIT")
    return available


def _legal_squad(squad: tuple[_Player, ...], rules: dict[str, object]) -> bool:
    if len(squad) != _rule_int(rules, "FPL-SQUAD-SIZE-001"):
        return False
    expected = _rule_map(rules, "FPL-SQUAD-POSITIONS-001")
    for position, count in expected.items():
        if sum(row.position == position for row in squad) != int(count):
            return False
    max_club = _rule_int(rules, "FPL-SQUAD-MAX-CLUB-001")
    counts: dict[int, int] = {}
    for row in squad:
        counts[row.team_id] = counts.get(row.team_id, 0) + 1
        if counts[row.team_id] > max_club:
            return False
    return True


def _incoming_groups(
    outgoing: tuple[_Owned, ...],
    *,
    players: tuple[_Player, ...],
    owned_ids: set[int],
):
    counts = {position: 0 for position in _POSITIONS}
    for row in outgoing:
        counts[row.position] += 1
    pools = {
        position: tuple(
            row for row in players if row.position == position and row.player_id not in owned_ids
        )
        for position in _POSITIONS
    }
    groups: list[tuple[tuple[_Player, ...], ...]] = []
    for position in _POSITIONS:
        count = counts[position]
        if count:
            groups.append(tuple(combinations(pools[position], count)))
    if not groups:
        yield ()
        return
    for selected in product(*groups):
        yield tuple(player for group in selected for player in group)


def _pair_transfers(
    outgoing: tuple[_Owned, ...],
    incoming: tuple[_Player, ...],
) -> tuple[tuple[int, int], ...]:
    moves: list[tuple[int, int]] = []
    for position in _POSITIONS:
        out_ids = sorted(row.player_id for row in outgoing if row.position == position)
        in_ids = sorted(row.player_id for row in incoming if row.position == position)
        if len(out_ids) != len(in_ids):
            raise ValueError("transfer position counts do not reconcile")
        moves.extend(zip(out_ids, in_ids, strict=True))
    return tuple(sorted(moves))


def _normal_actions(
    *,
    state: dict[str, object],
    owned: tuple[_Owned, ...],
    players: tuple[_Player, ...],
    chip: str,
    max_transfers: int,
    rules: dict[str, object],
    budget: _Budget,
):
    by_id = {row.player_id: row for row in players}
    current = tuple(by_id[row.player_id] for row in owned)
    owned_ids = {row.player_id for row in owned}
    bank = _as_int(state.get("bank_tenths"), label="manager bank")
    free_transfers = _as_int(state.get("free_transfers"), label="manager free_transfers")
    hit_cost = _rule_int(rules, "FPL-EXTRA-TRANSFER-HIT-POINTS-001")
    for transfer_count in range(max_transfers + 1):
        for outgoing_combo in combinations(owned, transfer_count):
            outgoing = tuple(outgoing_combo)
            outgoing_ids = {row.player_id for row in outgoing}
            retained = tuple(row for row in current if row.player_id not in outgoing_ids)
            sale_value = sum(row.selling_price for row in outgoing)
            for incoming in _incoming_groups(
                outgoing,
                players=players,
                owned_ids=owned_ids,
            ):
                budget.consume()
                incoming_cost = sum(row.price for row in incoming)
                bank_after = bank + sale_value - incoming_cost
                if bank_after < 0:
                    continue
                squad = tuple(
                    sorted((*retained, *incoming), key=lambda row: row.player_id)
                )
                if not _legal_squad(squad, rules):
                    continue
                extra = max(0, transfer_count - free_transfers)
                yield _SquadAction(
                    chip=chip,
                    transfers=_pair_transfers(outgoing, incoming),
                    squad=squad,
                    bank_after=bank_after,
                    hit_points=extra * hit_cost,
                )


def _full_rebuild_actions(
    *,
    state: dict[str, object],
    owned: tuple[_Owned, ...],
    players: tuple[_Player, ...],
    chip: str,
    rules: dict[str, object],
    budget: _Budget,
):
    counts = {
        position: int(value)
        for position, value in _rule_map(rules, "FPL-SQUAD-POSITIONS-001").items()
    }
    owned_by_id = {row.player_id: row for row in owned}
    owned_ids = set(owned_by_id)
    available_budget = _as_int(state.get("bank_tenths"), label="manager bank") + sum(
        row.selling_price for row in owned
    )
    by_position = {
        position: tuple(row for row in players if row.position == position)
        for position in _POSITIONS
    }
    choice_groups = [
        combinations(by_position[position], counts[position])
        for position in _POSITIONS
    ]
    max_club = _rule_int(rules, "FPL-SQUAD-MAX-CLUB-001")
    for grouped in product(*choice_groups):
        budget.consume()
        squad = tuple(
            sorted(
                (player for group in grouped for player in group),
                key=lambda row: row.player_id,
            )
        )
        club_counts: dict[int, int] = {}
        legal = True
        for player in squad:
            club_counts[player.team_id] = club_counts.get(player.team_id, 0) + 1
            if club_counts[player.team_id] > max_club:
                legal = False
                break
        if not legal:
            continue
        cost = sum(
            owned_by_id[player.player_id].selling_price
            if player.player_id in owned_by_id
            else player.price
            for player in squad
        )
        if cost > available_budget or not _legal_squad(squad, rules):
            continue
        selected = {row.player_id for row in squad}
        outgoing = tuple(row for row in owned if row.player_id not in selected)
        incoming = tuple(row for row in squad if row.player_id not in owned_ids)
        bank_during = available_budget - cost
        yield _SquadAction(
            chip=chip,
            transfers=_pair_transfers(outgoing, incoming),
            squad=squad,
            bank_after=(
                _as_int(state.get("bank_tenths"), label="manager bank")
                if chip == "FREE_HIT"
                else bank_during
            ),
            hit_points=0,
        )


def _lineup_limits(rules: dict[str, object]) -> tuple[dict[str, int], dict[str, int]]:
    minimum = {
        position: int(value)
        for position, value in _rule_map(rules, "FPL-XI-POSITION-MIN-001").items()
    }
    maximum = {
        position: int(value)
        for position, value in _rule_map(rules, "FPL-XI-POSITION-MAX-001").items()
    }
    return minimum, maximum


def _legal_lineups(squad: tuple[_Player, ...], rules: dict[str, object]):
    minimum, maximum = _lineup_limits(rules)
    by_position = {
        position: tuple(sorted(row.player_id for row in squad if row.position == position))
        for position in _POSITIONS
    }
    xi_size = _rule_int(rules, "FPL-XI-SIZE-001")
    for goalkeeper in by_position["GK"]:
        for defenders in range(minimum["DEF"], maximum["DEF"] + 1):
            for mids in range(minimum["MID"], maximum["MID"] + 1):
                forwards = xi_size - 1 - defenders - mids
                if not minimum["FWD"] <= forwards <= maximum["FWD"]:
                    continue
                for defs in combinations(by_position["DEF"], defenders):
                    for midfielders in combinations(by_position["MID"], mids):
                        for fwds in combinations(by_position["FWD"], forwards):
                            yield tuple(sorted((goalkeeper, *defs, *midfielders, *fwds)))


def _missing_count_distribution(
    starter_ids: tuple[int, ...],
    *,
    positions: dict[int, str],
    appearance: dict[int, Fraction],
) -> dict[tuple[int, int, int], Fraction]:
    """Convolve per-position missing-count distributions independently."""

    per_position: dict[str, dict[int, Fraction]] = {}
    for position in _OUTFIELD:
        distribution = {0: Fraction(1, 1)}
        for player_id in (item for item in starter_ids if positions[item] == position):
            p = appearance[player_id]
            updated: dict[int, Fraction] = {}
            for missing, probability in distribution.items():
                updated[missing] = updated.get(missing, Fraction(0, 1)) + probability * p
                updated[missing + 1] = (
                    updated.get(missing + 1, Fraction(0, 1))
                    + probability * (1 - p)
                )
            distribution = updated
        per_position[position] = distribution

    result: dict[tuple[int, int, int], Fraction] = {}
    for d, pd in per_position["DEF"].items():
        for m, pm in per_position["MID"].items():
            for f, pf in per_position["FWD"].items():
                result[(d, m, f)] = pd * pm * pf
    return result


def _formation_legal(
    counts: dict[str, int],
    minimum: dict[str, int],
    maximum: dict[str, int],
) -> bool:
    return all(minimum[p] <= counts[p] <= maximum[p] for p in _OUTFIELD)


def _bench_weights(
    *,
    xi_ids: tuple[int, ...],
    squad_ids: tuple[int, ...],
    positions: dict[int, str],
    appearance: dict[int, Fraction],
    order: tuple[int, ...],
    minimum: dict[str, int],
    maximum: dict[str, int],
) -> dict[int, Fraction]:
    bench_ids = tuple(sorted(set(squad_ids) - set(xi_ids)))
    start_gk = tuple(pid for pid in xi_ids if positions[pid] == "GK")
    bench_gk = tuple(pid for pid in bench_ids if positions[pid] == "GK")
    if len(start_gk) != 1 or len(bench_gk) != 1:
        raise ValueError("reference solver lineup requires one starting/bench goalkeeper")
    weights = {bench_gk[0]: 1 - appearance[start_gk[0]]}
    outfield_starters = tuple(pid for pid in xi_ids if positions[pid] != "GK")
    bench_outfield = tuple(pid for pid in bench_ids if positions[pid] != "GK")
    if len(order) != 3 or set(order) != set(bench_outfield):
        raise ValueError("reference solver bench order mismatch")

    missing_distribution = _missing_count_distribution(
        outfield_starters,
        positions=positions,
        appearance=appearance,
    )
    planned = {
        position: sum(positions[player_id] == position for player_id in outfield_starters)
        for position in _OUTFIELD
    }
    selected_probability = {player_id: Fraction(0, 1) for player_id in order}
    bench_probabilities = tuple(appearance[player_id] for player_id in order)
    for missing, p_missing in missing_distribution.items():
        if p_missing == 0 or not any(missing):
            continue
        for bits in product((0, 1), repeat=3):
            p_state = p_missing
            for bit, p_appear in zip(bits, bench_probabilities, strict=True):
                p_state *= p_appear if bit else 1 - p_appear
            if p_state == 0:
                continue
            live = dict(planned)
            remaining = {
                "DEF": missing[0],
                "MID": missing[1],
                "FWD": missing[2],
            }
            for player_id, appears in zip(order, bits, strict=True):
                if not appears or not any(remaining.values()):
                    continue
                for missing_position in _OUTFIELD:
                    if remaining[missing_position] == 0:
                        continue
                    trial = dict(live)
                    trial[missing_position] -= 1
                    trial[positions[player_id]] += 1
                    if not _formation_legal(trial, minimum, maximum):
                        continue
                    live = trial
                    remaining[missing_position] -= 1
                    selected_probability[player_id] += p_state
                    break
    for player_id in order:
        p = appearance[player_id]
        weights[player_id] = (
            selected_probability[player_id] / p if p > 0 else Fraction(0, 1)
        )
    return weights


def _captain_choice(
    xi_ids: tuple[int, ...],
    values: dict[int, _Value],
    *,
    multiplier: int,
) -> tuple[int, int, Fraction]:
    if multiplier < 2:
        raise ValueError("captain multiplier must be >= 2")
    best: tuple[Fraction, int, int, int, int] | None = None
    copies = multiplier - 1
    for captain in xi_ids:
        captain_value = values[captain]
        no_show = 1 - captain_value.appearance_probability
        for vice in xi_ids:
            if vice == captain:
                continue
            bonus = copies * (
                captain_value.expected_points + no_show * values[vice].expected_points
            )
            key = (bonus, -captain, -vice, captain, vice)
            if best is None or key[:3] > best[:3]:
                best = key
    if best is None:
        raise ValueError("captain/vice selection requires two XI players")
    return best[3], best[4], best[0]


def _optimise_submission(
    squad: tuple[_Player, ...],
    values: dict[int, _Value],
    *,
    chip: str,
    hit_points: int,
    rules: dict[str, object],
) -> _Submission:
    positions = {row.player_id: row.position for row in squad}
    squad_ids = tuple(sorted(positions))
    expected = {pid: values[pid].expected_points for pid in squad_ids}
    appearance = {pid: values[pid].appearance_probability for pid in squad_ids}
    total_squad = sum(expected.values(), Fraction(0, 1))
    minimum, maximum = _lineup_limits(rules)
    multiplier = (
        _rule_int(rules, "FPL-TRIPLE-CAPTAIN-MULTIPLIER-001")
        if chip == "TRIPLE_CAPTAIN"
        else _rule_int(rules, "FPL-CAPTAIN-MULTIPLIER-001")
    )

    best: tuple[Fraction, tuple[object, ...], _Submission] | None = None
    for xi_ids in _legal_lineups(squad, rules):
        bench_ids = tuple(sorted(set(squad_ids) - set(xi_ids)))
        bench_gks = tuple(pid for pid in bench_ids if positions[pid] == "GK")
        outfield = tuple(pid for pid in bench_ids if positions[pid] != "GK")
        if len(bench_gks) != 1 or len(outfield) != 3:
            continue
        captain, vice, captain_bonus = _captain_choice(
            xi_ids,
            values,
            multiplier=multiplier,
        )
        xi_points = sum((expected[pid] for pid in xi_ids), Fraction(0, 1))
        if chip == "BENCH_BOOST":
            bench_order = tuple(sorted(outfield))
            autosub = Fraction(0, 1)
            before_hits = total_squad + captain_bonus
        else:
            best_bench: tuple[Fraction, tuple[int, ...], tuple[int, ...]] | None = None
            for order in permutations(sorted(outfield)):
                weights = _bench_weights(
                    xi_ids=xi_ids,
                    squad_ids=squad_ids,
                    positions=positions,
                    appearance=appearance,
                    order=tuple(order),
                    minimum=minimum,
                    maximum=maximum,
                )
                autosub = sum(
                    (weights[player_id] * expected[player_id] for player_id in bench_ids),
                    Fraction(0, 1),
                )
                tie = tuple(-player_id for player_id in order)
                candidate = (autosub, tie, tuple(order))
                if (
                    best_bench is None
                    or candidate[0] > best_bench[0]
                    or (candidate[0] == best_bench[0] and candidate[1] > best_bench[1])
                ):
                    best_bench = candidate
            if best_bench is None:
                raise ValueError("reference solver found no bench order")
            autosub, _, bench_order = best_bench
            before_hits = xi_points + autosub + captain_bonus

        objective = before_hits - hit_points
        submission = _Submission(
            xi_ids=xi_ids,
            captain_id=captain,
            vice_id=vice,
            bench_gk_id=bench_gks[0],
            bench_order=bench_order,
            xi_points=xi_points,
            autosub_points=autosub,
            captain_bonus=captain_bonus,
            squad_points_if_bench_boost=total_squad,
            points_before_hits=before_hits,
            objective=objective,
        )
        tie_key: tuple[object, ...] = (
            tuple(-pid for pid in xi_ids),
            -captain,
            -vice,
            tuple(-pid for pid in bench_order),
        )
        if (
            best is None
            or objective > best[0]
            or (objective == best[0] and tie_key > best[1])
        ):
            best = (objective, tie_key, submission)
    if best is None:
        raise ValueError("reference solver found no legal XI")
    return best[2]


def _ratio(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _action_payload(
    squad_action: _SquadAction,
    submission: _Submission,
) -> dict[str, object]:
    return {
        "chip": squad_action.chip,
        "transfers": [
            {
                "outgoing_player_id": outgoing,
                "incoming_player_id": incoming,
            }
            for outgoing, incoming in squad_action.transfers
        ],
        "squad_ids": [row.player_id for row in squad_action.squad],
        "xi_ids": list(submission.xi_ids),
        "captain_id": submission.captain_id,
        "vice_captain_id": submission.vice_id,
        "bench_gk_id": submission.bench_gk_id,
        "outfield_bench_order": list(submission.bench_order),
        "bank_after_tenths": squad_action.bank_after,
        "mechanics": {
            "xi_points": _ratio(submission.xi_points),
            "autosub_points": _ratio(submission.autosub_points),
            "captain_bonus": _ratio(submission.captain_bonus),
            "squad_points_if_bench_boost": _ratio(
                submission.squad_points_if_bench_boost
            ),
            "points_before_hits": _ratio(submission.points_before_hits),
            "hit_points": squad_action.hit_points,
            "objective_points": _ratio(submission.objective),
        },
    }


def _action_tie_key(payload: dict[str, object]) -> tuple[object, ...]:
    transfers = payload["transfers"]
    squad_ids = payload["squad_ids"]
    xi_ids = payload["xi_ids"]
    return (
        -len(transfers),  # type: ignore[arg-type]
        _CHIP_RANK[str(payload["chip"])],
        tuple(-int(item) for item in squad_ids),  # type: ignore[arg-type]
        tuple(-int(item) for item in xi_ids),  # type: ignore[arg-type]
        -int(payload["captain_id"]),
        -int(payload["vice_captain_id"]),
    )


def solve_reference_request(request: ReferenceSolverRequest) -> ReferenceSolverRun:
    """Solve the exact declared tactical action surface or fail closed at the node limit."""

    actions_evaluated = 0
    incumbent_payload: dict[str, object] | None = None
    incumbent_objective: Fraction | None = None
    incumbent_tie: tuple[object, ...] | None = None
    budget = _Budget(request.max_search_nodes)

    try:
        decision_input = request.decision_input
        state = request.manager_state
        forecast = request.forecast
        universe = request.candidate_universe
        rules = _rules(request.ruleset)
        policy = request.decision_policy

        if decision_input.get("use_mode") not in {"SHADOW", "PRODUCTION"}:
            raise ValueError("reference solver DecisionInput use_mode invalid")
        if policy.get("tie_break_policy") != "lexicographic-official-id-v1":
            raise ValueError("reference solver v1 does not implement requested tie-break policy")
        gameweek = _as_int(decision_input.get("gameweek"), label="decision gameweek", positive=True)
        max_transfers = _as_int(
            decision_input.get("max_normal_transfers"),
            label="max_normal_transfers",
        )
        if not 0 <= max_transfers <= 15:
            raise ValueError("max_normal_transfers outside [0,15]")
        chips = decision_input.get("chips_considered")
        if not isinstance(chips, list) or "NONE" not in chips:
            raise ValueError("DecisionInput chips_considered must contain NONE")
        if any(str(chip) not in _CHIP_RANK for chip in chips):
            raise ValueError("DecisionInput contains unsupported chip")

        players = _parse_players(universe)
        owned = _parse_owned(state)
        _validate_owned_matches(owned, players)
        values = _build_values(
            forecast,
            gameweek=gameweek,
            player_ids=(row.player_id for row in players),
        )
        available = _available_chips(state, rules)

        for chip in sorted({str(item) for item in chips}):
            if chip not in available:
                continue
            if chip in {"WILDCARD", "FREE_HIT"}:
                squad_actions = _full_rebuild_actions(
                    state=state,
                    owned=owned,
                    players=players,
                    chip=chip,
                    rules=rules,
                    budget=budget,
                )
            else:
                squad_actions = _normal_actions(
                    state=state,
                    owned=owned,
                    players=players,
                    chip=chip,
                    max_transfers=max_transfers,
                    rules=rules,
                    budget=budget,
                )
            for squad_action in squad_actions:
                squad_values = {
                    row.player_id: values[row.player_id] for row in squad_action.squad
                }
                submission = _optimise_submission(
                    squad_action.squad,
                    squad_values,
                    chip=chip,
                    hit_points=squad_action.hit_points,
                    rules=rules,
                )
                payload = _action_payload(squad_action, submission)
                objective = submission.objective
                tie = _action_tie_key(payload)
                actions_evaluated += 1
                if (
                    incumbent_payload is None
                    or objective > incumbent_objective  # type: ignore[operator]
                    or (objective == incumbent_objective and tie > incumbent_tie)  # type: ignore[operator]
                ):
                    incumbent_payload = payload
                    incumbent_objective = objective
                    incumbent_tie = tie
    except _SearchLimit as exc:
        tie_break = str(request.decision_policy.get("tie_break_policy") or "")
        if incumbent_payload is None or incumbent_objective is None:
            return ReferenceSolverRun(
                request_id=request.request_id,
                solver_status=ReferenceSolverRunStatus.SOLVER_LIMIT,
                best_objective=None,
                best_bound=None,
                gap=None,
                selected_action_id=None,
                selected_action_json=None,
                action_surface_complete=False,
                tie_break_policy_id=tie_break,
                nodes_evaluated=budget.nodes,
                actions_evaluated=actions_evaluated,
                limit_reason=str(exc),
            )
        selected_json = canonical_json_bytes(incumbent_payload).decode("utf-8")
        selected_id = canonical_sha256(
            {"schema_name": "apex-decision-action", **incumbent_payload}
        )
        return ReferenceSolverRun(
            request_id=request.request_id,
            solver_status=ReferenceSolverRunStatus.SOLVER_LIMIT,
            best_objective=ExactSolverValue(
                incumbent_objective.numerator,
                incumbent_objective.denominator,
            ),
            best_bound=None,
            gap=None,
            selected_action_id=selected_id,
            selected_action_json=selected_json,
            action_surface_complete=False,
            tie_break_policy_id=tie_break,
            nodes_evaluated=budget.nodes,
            actions_evaluated=actions_evaluated,
            limit_reason=str(exc),
        )
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        return ReferenceSolverRun(
            request_id=request.request_id,
            solver_status=ReferenceSolverRunStatus.ERROR,
            best_objective=None,
            best_bound=None,
            gap=None,
            selected_action_id=None,
            selected_action_json=None,
            action_surface_complete=False,
            tie_break_policy_id=None,
            nodes_evaluated=budget.nodes,
            actions_evaluated=actions_evaluated,
            limit_reason=f"{type(exc).__name__}: {exc}",
        )

    tie_break = str(request.decision_policy.get("tie_break_policy") or "")
    if incumbent_payload is None or incumbent_objective is None:
        return ReferenceSolverRun(
            request_id=request.request_id,
            solver_status=ReferenceSolverRunStatus.INFEASIBLE,
            best_objective=None,
            best_bound=None,
            gap=None,
            selected_action_id=None,
            selected_action_json=None,
            action_surface_complete=True,
            tie_break_policy_id=tie_break,
            nodes_evaluated=budget.nodes,
            actions_evaluated=actions_evaluated,
        )

    selected_json = canonical_json_bytes(incumbent_payload).decode("utf-8")
    selected_id = canonical_sha256(
        {"schema_name": "apex-decision-action", **incumbent_payload}
    )
    exact = ExactSolverValue(incumbent_objective.numerator, incumbent_objective.denominator)
    return ReferenceSolverRun(
        request_id=request.request_id,
        solver_status=ReferenceSolverRunStatus.OPTIMAL,
        best_objective=exact,
        best_bound=exact,
        gap=ExactSolverValue.zero(),
        selected_action_id=selected_id,
        selected_action_json=selected_json,
        action_surface_complete=True,
        tie_break_policy_id=tie_break,
        nodes_evaluated=budget.nodes,
        actions_evaluated=actions_evaluated,
    )
