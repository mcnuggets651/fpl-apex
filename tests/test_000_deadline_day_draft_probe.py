import json

import requests


def test_deadline_day_draft_probe():
    base = "https://draft.premierleague.com/api"
    league_id = 33160
    headers = {"User-Agent": "Mozilla/5.0 ApexDeadlineProbe/1.0", "Accept": "application/json"}

    def get(path):
        r = requests.get(f"{base}{path}", timeout=30, headers=headers)
        r.raise_for_status()
        return r.json()

    bootstrap = get("/bootstrap-static")
    status_payload = get(f"/league/{league_id}/element-status")
    status_rows = status_payload.get("element_status") or []
    status_by_id = {int(r["element"]): r for r in status_rows}

    targets = [
        "barcola", "fernandez-pardo", "fernández-pardo", "mbaye", "harwood-bellis",
        "ahanor", "ansah", "fofana", "azeez", "balogun", "grealish", "ndiaye",
        "danso", "allan elias", "elias", "camara", "flemming", "brobbey",
        "goretzka", "diouf", "cho", "palacios", "wissa", "nketiah", "strand larsen",
    ]

    rows = []
    for e in bootstrap.get("elements") or []:
        fields = " ".join(str(e.get(k) or "") for k in ["web_name", "first_name", "second_name"]).lower()
        if any(t in fields for t in targets):
            pid = int(e["id"])
            s = status_by_id.get(pid, {})
            rows.append({
                "id": pid,
                "name": e.get("web_name") or e.get("second_name"),
                "first_name": e.get("first_name"),
                "second_name": e.get("second_name"),
                "element_type": e.get("element_type"),
                "team": e.get("team"),
                "status": s.get("status"),
                "owner": s.get("owner"),
                "total_points": e.get("total_points"),
                "form": e.get("form"),
                "selected_by_percent": e.get("selected_by_percent"),
            })

    # Also surface all currently available players that were newly added at the tail of the Draft IDs.
    # This catches deadline-day additions whose names were not known when this diagnostic was authored.
    available_tail = []
    for e in bootstrap.get("elements") or []:
        pid = int(e["id"])
        s = status_by_id.get(pid, {})
        if pid >= 620 and s.get("status") == "a":
            available_tail.append({
                "id": pid,
                "name": e.get("web_name") or e.get("second_name"),
                "element_type": e.get("element_type"),
                "team": e.get("team"),
                "total_points": e.get("total_points"),
                "form": e.get("form"),
            })

    payload = {"targets": rows, "available_tail": available_tail}
    raise AssertionError("DEADLINE_DRAFT_PROBE=" + json.dumps(payload, ensure_ascii=False, sort_keys=True))
