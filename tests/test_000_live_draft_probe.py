import json

import requests


def test_live_draft_waiver_probe():
    base = "https://draft.premierleague.com/api"
    league_id = 33160
    headers = {"User-Agent": "Mozilla/5.0 ApexDraftProbe/1.0", "Accept": "application/json"}

    def get(path):
        response = requests.get(f"{base}{path}", timeout=30, headers=headers)
        response.raise_for_status()
        return response.json()

    details = get(f"/league/{league_id}/details")
    status_payload = get(f"/league/{league_id}/element-status")
    bootstrap = get("/bootstrap-static")

    entries = details.get("league_entries") or []
    waiver_order = [
        {
            "entry_name": e.get("entry_name"),
            "manager": f"{e.get('player_first_name','')} {e.get('player_last_name','')}".strip(),
            "entry_id": e.get("entry_id"),
            "waiver_pick": e.get("waiver_pick"),
        }
        for e in sorted(entries, key=lambda x: x.get("waiver_pick") or 999)
    ]

    elements = bootstrap.get("elements") or []
    by_id = {int(e["id"]): e for e in elements if e.get("id") is not None}
    status_rows = status_payload.get("element_status") or []
    status_by_id = {int(r["element"]): r for r in status_rows}

    def label(e):
        pid = int(e["id"])
        s = status_by_id.get(pid, {})
        return {
            "id": pid,
            "name": e.get("web_name") or e.get("second_name"),
            "element_type": e.get("element_type"),
            "status": s.get("status"),
            "owner": s.get("owner"),
        }

    named = {}
    for e in elements:
        web = (e.get("web_name") or "").lower()
        second = (e.get("second_name") or "").lower()
        if any(key in web or key in second for key in ["nketiah", "strand larsen", "barcola", "osula"]):
            named[e.get("web_name") or e.get("second_name")] = label(e)

    available_forwards = []
    for e in elements:
        if int(e.get("element_type") or 0) != 4:
            continue
        pid = int(e["id"])
        s = status_by_id.get(pid, {})
        if s.get("status") == "a":
            available_forwards.append(label(e))

    payload = {
        "waiver_order": waiver_order,
        "named": named,
        "available_forwards": available_forwards,
    }
    raise AssertionError("LIVE_DRAFT_PROBE=" + json.dumps(payload, ensure_ascii=False, sort_keys=True))
