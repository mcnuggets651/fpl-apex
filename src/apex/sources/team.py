from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import requests
from apex.domain.models import OfficialSnapshot, TeamState, ExecutionDecision
from apex.domain.rules import calculate_selling_price, derive_next_free_transfers, season_rules
BASE = 'https://fantasy.premierleague.com/api'

def _dt(value):
    d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)

def replay_free_transfers(history: dict[str, Any], latest_event: int, latest_entry_history: dict | None=None, latest_active_chip: str | None=None, season='2026-2027') -> int:
    rules = season_rules(season)
    rows = {int(r['event']): dict(r) for r in history.get('current', []) if r.get('event') is not None and int(r['event']) <= latest_event}
    if latest_entry_history:
        r = dict(latest_entry_history)
        r.setdefault('event', latest_event)
        rows[latest_event] = r
    chips = {int(r['event']): str(r.get('name', '')).casefold().replace('_', '') for r in history.get('chips', []) if r.get('event') is not None}
    if latest_active_chip:
        chips[latest_event] = str(latest_active_chip).casefold().replace('_', '')
    ft = rules.initial_free_transfers
    for gw in range(1, latest_event + 1):
        transfers = int(rows.get(gw, {}).get('event_transfers', 0) or 0)
        chip = chips.get(gw)
        if chip in {'wildcard', 'freehit'}:
            ft = min(rules.max_rolled_free_transfers, max(rules.first_post_deadline_free_transfers, ft))
        else:
            ft = derive_next_free_transfers(ft, transfers, rules=rules, next_gameweek=gw + 1)
    return ft

def fetch_team_state(entry_id: int, official: OfficialSnapshot, *, session: requests.Session | None=None, timeout=20.0, now: datetime | None=None) -> TeamState | None:
    http = session or requests.Session()
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    elapsed = sorted((gw for gw, deadline in official.deadlines.items() if _dt(deadline) <= now), reverse=True)
    if not elapsed:
        return None
    chosen = None
    published = None
    for gw in elapsed:
        r = http.get(f'{BASE}/entry/{int(entry_id)}/event/{gw}/picks/', timeout=timeout)
        if r.status_code != 200:
            continue
        p = r.json()
        picks = p.get('picks', []) if isinstance(p, dict) else []
        if len(picks) == 15:
            chosen = p
            published = gw
            break
    if chosen is None:
        return None
    h = http.get(f'{BASE}/entry/{int(entry_id)}/history/', timeout=timeout)
    h.raise_for_status()
    history = h.json()
    entry_history = chosen.get('entry_history') or {}
    bank = int(entry_history.get('bank', 0) or 0)
    active = chosen.get('active_chip')
    ft = replay_free_transfers(history, published, entry_history, active, official.season)
    squad = tuple(sorted((int(r['element']) for r in chosen['picks'])))
    purchase = {}
    selling = {}
    complete = True
    players = official.player_map()
    for row in chosen['picks']:
        pid = int(row['element'])
        pp = row.get('purchase_price')
        sp = row.get('selling_price')
        if pp is not None:
            purchase[pid] = int(pp)
        if sp is not None:
            selling[pid] = int(sp)
    if len(purchase) != 15:
        complete = False
    if len(selling) != 15 and len(purchase) == 15:
        selling = {pid: calculate_selling_price(purchase[pid], players[pid].price_tenths) for pid in squad}
        complete = True
    elif len(selling) != 15:
        complete = False
    return TeamState(1, int(entry_id), int(published), squad, bank, ft, purchase, selling, str(active) if active else None, complete)

def apply_execution_overlay(state: TeamState, execution: ExecutionDecision | None, official: OfficialSnapshot) -> TeamState:
    if execution is None:
        return state
    squad = tuple(sorted(execution.squad_ids))
    players = official.player_map()
    if set(squad) - set(players):
        raise ValueError('execution overlay contains unknown Official FPL IDs')
    purchase = dict(state.purchase_prices_tenths)
    selling = dict(state.selling_prices_tenths)
    for pid in execution.transfers_out:
        purchase.pop(pid, None)
        selling.pop(pid, None)
    for pid in execution.transfers_in:
        purchase[pid] = players[pid].price_tenths
        selling[pid] = players[pid].price_tenths
    return TeamState(state.schema_version, state.entry_id, state.published_gw, squad, state.bank_tenths, state.free_transfers, purchase, selling, state.active_chip, len(purchase) == 15 and len(selling) == 15)
