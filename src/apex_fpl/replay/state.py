from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from apex_fpl.rules import season_rules


_VALID_CHIPS = {"wildcard", "free_hit", "bench_boost", "triple_captain"}


def advance_free_transfers(
    *,
    season: str,
    gameweek: int,
    free_transfers_before: int,
    permanent_transfers: int,
    active_chip: str | None,
) -> int:
    """Return FTs available for the next deadline under versioned rules."""
    rules = season_rules(season)
    chip = str(active_chip or "").casefold().replace("-", "_")
    if chip in {"wildcard", "free_hit"}:
        after = max(rules.first_post_deadline_free_transfers, free_transfers_before)
    else:
        after = max(
            rules.first_post_deadline_free_transfers,
            int(free_transfers_before) - int(permanent_transfers) + 1,
        )
    after = min(rules.max_rolled_free_transfers, after)
    top_up = rules.top_up_for_gameweek(int(gameweek) + 1)
    if top_up is not None:
        after = min(rules.max_rolled_free_transfers, max(after, top_up))
    return int(after)


@dataclass(frozen=True)
class WeeklyAction:
    gameweek: int
    transfers: tuple[tuple[int, int], ...]
    chip: str | None
    squad: tuple[int, ...]
    xi: tuple[int, ...]
    bench_order: tuple[int, ...]
    captain_id: int
    vice_captain_id: int
    hit_cost: int

    def __post_init__(self) -> None:
        if len(self.squad) != 15 or len(set(self.squad)) != 15:
            raise ValueError("weekly action requires 15 unique squad players")
        if len(self.xi) != 11 or len(set(self.xi)) != 11:
            raise ValueError("weekly action requires 11 unique starters")
        if not set(self.xi).issubset(self.squad):
            raise ValueError("starting XI must be contained in the squad")
        if len(self.bench_order) != 4 or set(self.bench_order) != set(self.squad) - set(self.xi):
            raise ValueError("bench order must contain every non-starter exactly once")
        if self.captain_id not in self.xi or self.vice_captain_id not in self.xi:
            raise ValueError("captain and vice-captain must start")
        if self.captain_id == self.vice_captain_id:
            raise ValueError("captain and vice-captain must differ")
        if self.chip is not None and self.chip not in _VALID_CHIPS:
            raise ValueError(f"unsupported chip: {self.chip}")
        if int(self.hit_cost) < 0 or int(self.hit_cost) % 4:
            raise ValueError("hit cost must be a non-negative multiple of four")

    def to_dict(self) -> dict:
        return {
            "gameweek": int(self.gameweek),
            "transfers": [
                {"player_out": int(player_out), "player_in": int(player_in)}
                for player_out, player_in in self.transfers
            ],
            "chip": self.chip,
            "squad": list(self.squad),
            "xi": list(self.xi),
            "bench_order": list(self.bench_order),
            "captain_id": int(self.captain_id),
            "vice_captain_id": int(self.vice_captain_id),
            "hit_cost": int(self.hit_cost),
        }


@dataclass(frozen=True)
class ReplayState:
    season: str
    next_gameweek: int
    squad: tuple[int, ...]
    bank: float
    free_transfers: int
    purchase_prices: tuple[tuple[int, float], ...]
    chips_used: tuple[tuple[int, str], ...] = ()
    previous_state_sha256: str | None = None

    def __post_init__(self) -> None:
        rules = season_rules(self.season)
        if len(self.squad) != 15 or len(set(self.squad)) != 15:
            raise ValueError("replay state requires 15 unique permanent players")
        if not 0 <= int(self.free_transfers) <= rules.max_rolled_free_transfers:
            raise ValueError("free-transfer balance is outside season rules")
        if float(self.bank) < 0:
            raise ValueError("bank cannot be negative")
        price_ids = [int(player_id) for player_id, _ in self.purchase_prices]
        if set(price_ids) != set(self.squad) or len(price_ids) != len(set(price_ids)):
            raise ValueError("purchase-price ledger must match the permanent squad")
        for _, chip in self.chips_used:
            if chip not in _VALID_CHIPS:
                raise ValueError(f"unsupported chip in state: {chip}")

    def to_dict(self) -> dict:
        return {
            "season": self.season,
            "next_gameweek": int(self.next_gameweek),
            "squad": list(self.squad),
            "bank": round(float(self.bank), 4),
            "free_transfers": int(self.free_transfers),
            "purchase_prices": [
                {"player_id": int(player_id), "price": float(price)}
                for player_id, price in sorted(self.purchase_prices)
            ],
            "chips_used": [
                {"gameweek": int(gameweek), "chip": chip}
                for gameweek, chip in self.chips_used
            ],
            "previous_state_sha256": self.previous_state_sha256,
        }

    @property
    def state_sha256(self) -> str:
        payload = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
