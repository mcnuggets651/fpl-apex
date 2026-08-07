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
    selling_prices: dict[int, float] = field(default_factory=dict)
    selling_prices_exact: bool = False
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
    sf = Path(state_path)
    if sf.exists():
        raw = yaml.safe_load(sf.read_text()) or {}
        bank = float(raw.get("bank", 0.0))
        free = int(raw.get("free_transfers", 1))
        selling_prices = {
            int(pid): float(price)
            for pid, price in (raw.get("selling_prices", {}) or {}).items()
        }
    free = min(5, max(1, free))
    return TeamState(
        squad=squad,
        bank=bank,
        free_transfers=free,
        source="manual_override",
        selling_prices=selling_prices,
        selling_prices_exact=bool(selling_prices),
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

    FPL does not expose the purchase price of a manager's original GW1 players in
    the public picks endpoint. Capturing the official pre-deadline price universe
    closes that gap for later weekly transfer calculations.
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
    purchase_t = int(round(float(purchase) * 10))
    current_t = int(round(float(current) * 10))
    if current_t <= purchase_t:
        return current_t / 10.0
    return (purchase_t + (current_t - purchase_t) // 2) / 10.0


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
    initial_price: dict[int, float] = {}
    if initial_prices_path and initial_prices_path.exists():
        initial = pd.read_csv(initial_prices_path)
        if {"player_id", "price"}.issubset(initial.columns):
            initial_price = {
                int(row.player_id): float(row.price)
                for row in initial[["player_id", "price"]].itertuples(index=False)
            }

    latest_buy: dict[int, float] = {}
    latest_event: dict[int, int] = {}
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
    for pid in state.squad:
        current = current_price.get(pid)
        if current is None:
            exact = False
            continue
        purchase = latest_buy.get(pid, initial_price.get(pid))
        if purchase is None:
            # Safe public fallback: current price is exact for a player whose price
            # has not risen, but can overstate realised cash for a risen player.
            selling[pid] = current
            exact = False
        else:
            selling[pid] = _selling_price(purchase, current)
    return selling, exact and len(selling) == len(state.squad)


def resolve_team_state(
    http: CachedHttp,
    players: pd.DataFrame,
    events: pd.DataFrame,
    cache_dir: Path,
    current_squad_path: str | Path,
    team_state_path: str | Path,
    entry_id: int | None,
    force: bool = False,
) -> TeamStateResolution:
    # Capture the complete official GW1 price universe *before* the first deadline,
    # even though public entry picks do not exist yet. This is required later to
    # reconstruct exact selling prices for players owned from the original squad.
    initial_prices = persist_initial_prices(players, events, cache_dir)

    manual = load_team_state(current_squad_path, team_state_path)
    if manual is not None:
        return TeamStateResolution(
            state=manual,
            configured=True,
            ok=True,
            detail="manual override loaded; it takes priority over public entry state",
            metadata=manual.to_dict(),
        )

    if not entry_id:
        return TeamStateResolution(
            state=None,
            configured=False,
            ok=True,
            detail="no FPL entry ID configured; initial-squad mode",
        )

    client = OfficialEntryClient(http, int(entry_id))
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
        captured = "pre-GW1 price universe captured" if initial_prices else "pre-GW1 price capture unavailable"
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

    # If the first deadline has passed, use the previously cached pre-GW1 file.
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
        selling_prices=selling,
        selling_prices_exact=exact,
        public_deadline_snapshot=True,
    )
    pricing = "exact reconstructed selling prices" if exact else "partly approximate selling prices"
    detail = (
        f"FPL entry {public.entry_id} ({public.entry_name}) synced from published GW"
        f"{public.published_gw} picks; {public.free_transfers} FT; £{public.bank:.1f}m bank; "
        f"{pricing}. Public mode cannot see transfers made after the latest deadline."
    )
    return TeamStateResolution(
        state=state,
        configured=True,
        ok=True,
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