from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd
import yaml

from apex_fpl.data.entry import OfficialEntryClient, PublicEntryState
from apex_fpl.data.http import CachedHttp


@dataclass
class TeamState:
    squad: set[int]
    bank: float = 0.0
    free_transfers: int = 1
    source: str = "manual"
    entry_id: int | None = None
    entry_name: str = ""
    manager_name: str = ""
    published_gw: int | None = None
    team_value: float | None = None
    captain_id: int | None = None
    vice_captain_id: int | None = None
    active_chip: str | None = None
    chips_used: list[dict] = field(default_factory=list)
    selling_prices: dict[int, float] = field(default_factory=dict)
    selling_prices_exact: bool = False
    transfer_history_complete: bool = False
    public_deadline_snapshot: bool = False

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["squad"] = sorted(self.squad)
        payload["selling_prices"] = {
            str(pid): price for pid, price in sorted(self.selling_prices.items())
        }
        return payload


@dataclass
class TeamStateResolution:
    state: TeamState | None
    configured: bool
    ok: bool
    detail: str
    metadata: dict = field(default_factory=dict)


def load_team_state(
    squad_path: str | Path = "data/manual/current_squad.csv",
    state_path: str | Path = "data/manual/team_state.yaml",
) -> TeamState | None:
    """Load an explicit local override.

    Manual state intentionally has priority over the public FPL entry snapshot so
    the user can describe transfers already made after the latest deadline.
    """
    squad_file = Path(squad_path)
    if not squad_file.exists():
        return None
    df = pd.read_csv(squad_file)
    if "player_id" not in df.columns:
        raise ValueError("current_squad.csv requires a player_id column")
    squad = set(pd.to_numeric(df["player_id"], errors="raise").astype(int).tolist())
    if len(squad) != 15:
        raise ValueError("current_squad.csv must contain exactly 15 unique player_id values")

    bank, free = 0.0, 1
    selling_prices: dict[int, float] = {}
    chips_used: list[dict] = []
    sf = Path(state_path)
    if sf.exists():
        raw = yaml.safe_load(sf.read_text()) or {}
        bank = float(raw.get("bank", 0.0))
        free = int(raw.get("free_transfers", 1))
        selling_prices = {
            int(pid): float(price)
            for pid, price in (raw.get("selling_prices", {}) or {}).items()
        }
        chips_used = [
            dict(row)
            for row in (raw.get("chips_used", []) or [])
            if isinstance(row, dict)
        ]
    free = min(5, max(1, free))
    exact_prices = set(selling_prices) == squad and len(selling_prices) == 15
    return TeamState(
        squad=squad,
        bank=bank,
        free_transfers=free,
        source="manual_override",
        chips_used=chips_used,
        selling_prices=selling_prices,
        selling_prices_exact=exact_prices,
        # A manual override is an explicit user-supplied current state rather than
        # a claim about the public transfer endpoint. Complete selling prices are
        # sufficient for exact affordability in that mode.
        transfer_history_complete=exact_prices,
    )


def _initial_price_path(cache_dir: Path) -> Path:
    return cache_dir / "fpl_initial_prices_2026_27.csv"


def persist_initial_prices(
    players: pd.DataFrame,
    events: pd.DataFrame,
    cache_dir: Path,
    now: datetime | None = None,
) -> Path | None:
    """Persist pre-GW1 prices so public-entry selling values can be reconstructed.

    The cache is useful replay evidence, but weekly correctness no longer depends on
    it: Official FPL's ``cost_change_start`` field also lets Apex reconstruct the
    exact season-start price from a current bootstrap snapshot.
    """
    path = _initial_price_path(cache_dir)
    if path.exists():
        return path
    if events.empty or players.empty or "deadline_time" not in events:
        return None
    deadline = pd.to_datetime(events["deadline_time"], utc=True, errors="coerce").min()
    if pd.isna(deadline):
        return None
    now_ts = pd.Timestamp(now or datetime.now(timezone.utc))
    if now_ts.tzinfo is None:
        now_ts = now_ts.tz_localize("UTC")
    else:
        now_ts = now_ts.tz_convert("UTC")
    if now_ts >= deadline:
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = players[["player_id", "price"]].drop_duplicates("player_id").copy()
    out["price"] = pd.to_numeric(out["price"], errors="coerce")
    out.dropna().to_csv(path, index=False)
    return path


def _selling_price(purchase: float, current: float) -> float:
    """Return the FPL realised selling value using the half-profit rule in tenths."""
    purchase_t = int(round(float(purchase) * 10))
    current_t = int(round(float(current) * 10))
    if current_t <= purchase_t:
        return current_t / 10.0
    return (purchase_t + (current_t - purchase_t) // 2) / 10.0


def _season_start_prices(players: pd.DataFrame) -> dict[int, float]:
    """Reconstruct exact opening prices from the live Official bootstrap.

    ``cost_change_start`` is expressed in FPL tenths and is preserved on the raw
    Official player surface. Subtracting it from ``now_cost``/normalised ``price``
    is therefore an exact fallback when no pre-GW1 cache exists.
    """
    required = {"player_id", "price", "cost_change_start"}
    if not required.issubset(players.columns):
        return {}
    out: dict[int, float] = {}
    for row in players[list(required)].itertuples(index=False):
        pid = int(row.player_id)
        current = pd.to_numeric(pd.Series([row.price]), errors="coerce").iloc[0]
        delta = pd.to_numeric(
            pd.Series([row.cost_change_start]), errors="coerce"
        ).iloc[0]
        if pd.isna(current) or pd.isna(delta):
            continue
        current_t = int(round(float(current) * 10))
        start_t = current_t - int(round(float(delta)))
        if start_t > 0:
            out[pid] = start_t / 10.0
    return out


def _cached_initial_prices(path: Path | None) -> dict[int, float]:
    if path is None or not path.exists():
        return {}
    initial = pd.read_csv(path)
    if not {"player_id", "price"}.issubset(initial.columns):
        return {}
    initial["player_id"] = pd.to_numeric(initial["player_id"], errors="coerce")
    initial["price"] = pd.to_numeric(initial["price"], errors="coerce")
    initial = initial.dropna(subset=["player_id", "price"])
    return {
        int(row.player_id): float(row.price)
        for row in initial[["player_id", "price"]].itertuples(index=False)
    }


def _public_selling_prices(
    state: PublicEntryState,
    players: pd.DataFrame,
    initial_prices_path: Path | None,
) -> tuple[dict[int, float], bool]:
    current_price = {
        int(row.player_id): float(row.price)
        for row in players[["player_id", "price"]].itertuples(index=False)
        if pd.notna(row.price)
    }
    # Prefer a historically captured opening snapshot when available, then fill any
    # gaps from Official cost_change_start. Both are exact season-start values.
    initial_price = _season_start_prices(players)
    initial_price.update(_cached_initial_prices(initial_prices_path))

    latest_buy: dict[int, float] = {}
    latest_event: dict[int, int] = {}
    if state.transfers_complete:
        for tx in state.transfers:
            event = int(tx.get("event", 0) or 0)
            if event > state.published_gw:
                continue
            pid = tx.get("element_in")
            cost = tx.get("element_in_cost")
            if pid is None or cost is None:
                continue
            pid = int(pid)
            if event >= latest_event.get(pid, -1):
                latest_event[pid] = event
                latest_buy[pid] = float(cost) / 10.0

    selling: dict[int, float] = {}
    exact = True
    ledger_required = int(state.published_gw) >= 2
    if ledger_required and not state.transfers_complete:
        exact = False

    for pid in state.squad:
        current = current_price.get(pid)
        if current is None:
            exact = False
            continue
        # At the GW1 deadline every member of the public 15 is necessarily an
        # original squad selection, so a failed transfer endpoint cannot make its
        # purchase price ambiguous. From GW2 onward, a complete transfer ledger is
        # required to distinguish original players from later buys/re-buys.
        purchase = latest_buy.get(pid)
        if purchase is None and (state.transfers_complete or state.published_gw == 1):
            purchase = initial_price.get(pid)
        if purchase is None:
            selling[pid] = current
            exact = False
        else:
            selling[pid] = _selling_price(purchase, current)
    return selling, exact and len(selling) == len(state.squad)


def _actionable_state_ok(state: TeamState) -> bool:
    """Return whether a current 15 has exact cash semantics for transfer optimisation."""
    if len(state.squad) != 15:
        return False
    if state.bank < 0 or not 1 <= int(state.free_transfers) <= 5:
        return False
    price_ids = {int(pid) for pid in state.selling_prices}
    return bool(state.selling_prices_exact and price_ids == set(state.squad))


def resolve_team_state(
    http: CachedHttp,
    players: pd.DataFrame,
    events: pd.DataFrame,
    cache_dir: Path,
    current_squad_path: str | Path,
    team_state_path: str | Path,
    entry_id: int | None,
    force: bool = False,
    season: str = "2026-2027",
) -> TeamStateResolution:
    # Capture the complete official GW1 price universe *before* the first deadline
    # when possible. This remains useful provenance/replay evidence, while live
    # cost_change_start makes post-deadline reconstruction self-sufficient.
    initial_prices = persist_initial_prices(players, events, cache_dir)

    manual = load_team_state(current_squad_path, team_state_path)
    if manual is not None:
        ready = _actionable_state_ok(manual)
        detail = (
            "manual override loaded with exact 15-player selling-price state; it takes "
            "priority over public entry state"
            if ready
            else "manual override is incomplete for actionable transfer optimisation: "
            "provide the exact 15, bank/free-transfer state and realised selling price "
            "for every player"
        )
        return TeamStateResolution(
            state=manual,
            configured=True,
            ok=ready,
            detail=detail,
            metadata=manual.to_dict(),
        )

    if not entry_id:
        return TeamStateResolution(
            state=None,
            configured=False,
            ok=True,
            detail="no FPL entry ID configured; initial-squad mode",
        )

    client = OfficialEntryClient(http, int(entry_id), season=season)
    try:
        summary = client.summary(force=force)
        public = client.latest_public_state(events, force=force)
    except Exception as exc:
        return TeamStateResolution(
            state=None,
            configured=True,
            ok=False,
            detail=f"FPL entry {entry_id} sync failed: {type(exc).__name__}: {exc}",
        )

    entry_name = str(summary.get("name", f"Entry {entry_id}"))
    if public is None:
        captured = (
            "pre-GW1 price universe captured"
            if initial_prices
            else "pre-GW1 price capture unavailable"
        )
        return TeamStateResolution(
            state=None,
            configured=True,
            ok=True,
            detail=(
                f"FPL entry {entry_id} ({entry_name}) connected; no 15-player public "
                f"deadline squad is published yet, so Apex remains in initial-squad mode; {captured}"
            ),
            metadata={"entry_id": int(entry_id), "entry_name": entry_name},
        )

    if initial_prices is None:
        cached = _initial_price_path(cache_dir)
        initial_prices = cached if cached.exists() else None
    selling, exact = _public_selling_prices(public, players, initial_prices)
    state = TeamState(
        squad=public.squad,
        bank=public.bank,
        free_transfers=public.free_transfers,
        source="public_fpl_entry",
        entry_id=public.entry_id,
        entry_name=public.entry_name,
        manager_name=public.manager_name,
        published_gw=public.published_gw,
        team_value=public.team_value,
        captain_id=public.captain_id,
        vice_captain_id=public.vice_captain_id,
        active_chip=public.active_chip,
        chips_used=public.chips_used,
        selling_prices=selling,
        selling_prices_exact=exact,
        transfer_history_complete=public.transfers_complete,
        public_deadline_snapshot=True,
    )
    ready = _actionable_state_ok(state)
    pricing = (
        "exact reconstructed selling prices"
        if exact
        else "UNVERIFIED selling prices (actionable transfer optimisation blocked)"
    )
    ledger = (
        "complete public transfer ledger"
        if public.transfers_complete
        else "public transfer ledger unavailable"
    )
    detail = (
        f"FPL entry {public.entry_id} ({public.entry_name}) synced from published GW"
        f"{public.published_gw} picks; {public.free_transfers} FT; £{public.bank:.1f}m bank; "
        f"{pricing}; {ledger}. Public mode cannot see transfers made after the latest "
        "deadline, so an explicit manual override remains authoritative if the manager "
        "has already changed the squad during the current Gameweek."
    )
    return TeamStateResolution(
        state=state,
        configured=True,
        ok=ready,
        detail=detail,
        metadata=state.to_dict(),
    )


def write_team_state_report(report_dir: Path, resolution: TeamStateResolution) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "configured": resolution.configured,
        "ok": resolution.ok,
        "detail": resolution.detail,
        "team_state": resolution.metadata,
    }
    (report_dir / "team_state.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
