#!/usr/bin/env python3
"""Export one AIrsenal prediction tag into the Apex forecast contract.

Usage: python scripts/export_airsenal.py AIRSENAL.sqlite TAG output.csv
AIrsenal predictions already include its playing-time model, so xMins is set to
90 here to avoid applying a second minutes penalty inside Apex.
"""
import csv
import sqlite3
import sys

db_path, tag, output = sys.argv[1:4]
db = sqlite3.connect(db_path)
rows = db.execute("""
  SELECT pp.player_id, f.gameweek, SUM(pp.predicted_points)
  FROM player_prediction pp JOIN fixture f ON f.fixture_id=pp.fixture_id
  WHERE pp.tag=? AND f.gameweek IS NOT NULL
  GROUP BY pp.player_id, f.gameweek
  ORDER BY pp.player_id, f.gameweek
""", (tag,)).fetchall()
if not rows:
    raise SystemExit(f"No AIrsenal predictions found for tag {tag!r}")
with open(output, "w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle)
    writer.writerow(["player_id", "gameweek", "expected_points", "expected_minutes", "confidence"])
    writer.writerows((*row, 90, 0.85) for row in rows)
print(f"Exported {len(rows)} player-gameweek rows to {output}")
