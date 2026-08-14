from pathlib import Path

path = Path("src/apex_fpl/evaluation/understat_player_ab.py")
text = path.read_text(encoding="utf-8")
old = '''    exact = unique_matches(core, "full_name_key", us, method="full_name")\n    matched_core_ids = set(pd.to_numeric(exact.get("player_id"), errors="coerce").dropna().astype(int))\n    matched_us_rows = set(pd.to_numeric(exact.get("_understat_row"), errors="coerce").dropna().astype(int))\n'''
new = '''    exact = unique_matches(core, "full_name_key", us, method="full_name")\n    matched_core_ids = (\n        set(pd.to_numeric(exact["player_id"], errors="coerce").dropna().astype(int))\n        if "player_id" in exact.columns\n        else set()\n    )\n    matched_us_rows = (\n        set(pd.to_numeric(exact["_understat_row"], errors="coerce").dropna().astype(int))\n        if "_understat_row" in exact.columns\n        else set()\n    )\n'''
if text.count(old) != 1:
    raise SystemExit(f"expected one Understat empty-match target, found {text.count(old)}")
path.write_text(text.replace(old, new), encoding="utf-8")
