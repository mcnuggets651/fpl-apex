"""Fantasy Premier League 2026/27 rules used by the optimiser.

Keep rule constants isolated so a future season can be updated without touching
modelling code. Values here mirror the official 2026/27 FPL rules announced by
Premier League in July 2026.
"""

BUDGET_MILLIONS = 100.0
SQUAD_SIZE = 15
STARTING_XI_SIZE = 11
MAX_PER_TEAM = 3
MAX_ROLLED_FREE_TRANSFERS = 5
TRANSFER_HIT_COST = 4.0

# Two sets: one before the GW19 deadline and one from GW20 onward.
CHIPS_PER_HALF = {"wildcard": 1, "free_hit": 1, "triple_captain": 1, "bench_boost": 1}

# Defensive contribution thresholds. Goalkeepers do not earn DC points.
DEFENSIVE_CONTRIBUTION_THRESHOLD = {"DEF": 10, "MID": 12, "FWD": 12}
DEFENSIVE_CONTRIBUTION_POINTS = 2.0
