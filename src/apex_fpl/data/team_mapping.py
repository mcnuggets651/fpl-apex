from __future__ import annotations


TEAM_ALIASES = {
    "AFC Bournemouth": "Bournemouth",
    "Brighton & Hove Albion": "Brighton",
    "Leeds United": "Leeds",
    "Leicester City": "Leicester",
    "Man City": "Manchester City",
    "Man United": "Manchester United",
    "Man Utd": "Manchester United",
    "Newcastle": "Newcastle United",
    "Nott'm Forest": "Nottingham Forest",
    "Nottingham Forest": "Nottingham Forest",
    "Sheffield Utd": "Sheffield United",
    "Spurs": "Tottenham",
    "Tottenham Hotspur": "Tottenham",
    "West Ham United": "West Ham",
    "Wolves": "Wolverhampton Wanderers",
    "Wolverhampton": "Wolverhampton Wanderers",
}


def canonical_team(name: str) -> str:
    value = " ".join(str(name).strip().split())
    return TEAM_ALIASES.get(value, value)
