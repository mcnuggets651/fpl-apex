import json
import requests


def test_draft_signing_watch_live():
    base = "https://draft.premierleague.com/api"
    league_id = 33160
    headers = {"User-Agent": "Mozilla/5.0 ApexDraftWatch/1.0", "Accept": "application/json"}

    def get(path):
        r = requests.get(f"{base}{path}", timeout=30, headers=headers)
        r.raise_for_status()
        return r.json()

    bootstrap = get("/bootstrap-static")
    status_payload = get(f"/league/{league_id}/element-status")
    status_by_id = {int(r["element"]): r for r in (status_payload.get("element_status") or [])}

    names = [
        "mbaye", "harwood-bellis", "harwood bellis", "ansah", "ahanor",
        "fernandez-pardo", "fernández-pardo", "fofana", "balogun", "barcola",
        "grealish", "nketiah", "strand larsen", "allan", "goretzka", "kone",
    ]

    matches = []
    for e in bootstrap.get("elements") or []:
        fields = " ".join(str(e.get(k) or "") for k in ["web_name", "first_name", "second_name"]).lower()
        if any(n in fields for n in names):
            pid = int(e["id"])
            s = status_by_id.get(pid, {})
            matches.append({
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
            })

    tail = []
    for e in bootstrap.get("elements") or []:
        pid = int(e["id"])
        if pid >= 620:
            s = status_by_id.get(pid, {})
            tail.append({
                "id": pid,
                "name": e.get("web_name") or e.get("second_name"),
                "element_type": e.get("element_type"),
                "team": e.get("team"),
                "status": s.get("status"),
                "owner": s.get("owner"),
            })

    raise AssertionError("DRAFT_SIGNING_WATCH=" + json.dumps({"matches": matches, "tail": tail}, ensure_ascii=False, sort_keys=True))
