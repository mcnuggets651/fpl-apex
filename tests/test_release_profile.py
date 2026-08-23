import pytest

from apex_fpl.services.release_profile import (
    INSEASON_PROFILE,
    LAUNCH_PROFILE,
    resolve_release_profile,
)


def _manifest(*, published_gw=None):
    if published_gw is None:
        team_state = None
        gameweeks = [1, 2, 3]
    else:
        squad = list(range(1, 16))
        team_state = {
            "configured": True,
            "ok": True,
            "state": {
                "squad": squad,
                "published_gw": published_gw,
                "selling_prices_exact": True,
                "selling_prices": {str(pid): 5.0 for pid in squad},
            },
        }
        gameweeks = [published_gw + 1, published_gw + 2]
    return {"gameweeks": gameweeks, "team_state": team_state}


def test_launch_profile_requires_pre_gw1_state():
    profile = resolve_release_profile(
        {"selector": LAUNCH_PROFILE.selector, "current_gameweek": 1},
        _manifest(),
    )
    assert profile == LAUNCH_PROFILE

    with pytest.raises(ValueError, match="invalid once a personal deadline squad exists"):
        resolve_release_profile(
            {"selector": LAUNCH_PROFILE.selector, "current_gameweek": 2},
            _manifest(published_gw=1),
        )


def test_inseason_profile_requires_exact_sealed_team_state():
    profile = resolve_release_profile(
        {"selector": INSEASON_PROFILE.selector, "current_gameweek": 2},
        _manifest(published_gw=1),
    )
    assert profile == INSEASON_PROFILE

    broken = _manifest(published_gw=1)
    broken["team_state"]["state"]["selling_prices_exact"] = False
    with pytest.raises(ValueError, match="exact realised selling prices"):
        resolve_release_profile(
            {"selector": INSEASON_PROFILE.selector, "current_gameweek": 2},
            broken,
        )


def test_unknown_selector_cannot_fall_through_to_another_profile():
    with pytest.raises(ValueError, match="unsupported release selector"):
        resolve_release_profile({"selector": "mystery"}, _manifest())
