from pathlib import Path

from apex_fpl.data.tactical import load_tactical_roles


def test_tracked_tactical_overrides_are_current_and_valid():
    """Fail fast when committed live tactical evidence has expired."""
    loaded = load_tactical_roles(Path("data/manual/tactical_roles.csv"))
    assert loaded["player_id"].is_unique
