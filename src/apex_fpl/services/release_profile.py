from __future__ import annotations

from dataclasses import dataclass
from typing import Any


LAUNCH_SELECTOR = "adaptive_gw1_launch_with_transfer_option_value"
INSEASON_SELECTOR = "receding_horizon_current_team_maximum_ev"


@dataclass(frozen=True)
class ReleaseProfile:
    name: str
    selector: str
    sensitivity_contract: str
    requires_personal_team_state: bool


LAUNCH_PROFILE = ReleaseProfile(
    name="pre_gw1_launch",
    selector=LAUNCH_SELECTOR,
    sensitivity_contract="apex-adversarial-launch-ban-v2",
    requires_personal_team_state=False,
)
INSEASON_PROFILE = ReleaseProfile(
    name="in_season_receding_horizon",
    selector=INSEASON_SELECTOR,
    sensitivity_contract="apex-inseason-action-sensitivity-v1",
    requires_personal_team_state=True,
)


def resolve_release_profile(
    recommendation: dict[str, Any],
    manifest: dict[str, Any],
) -> ReleaseProfile:
    """Resolve the only valid release profile from selector + sealed lifecycle state.

    Release mode is not inferred from workflow names. The canonical selector and the
    sealed DecisionBundle must agree about lifecycle or certification fails closed.
    """
    selector = str(recommendation.get("selector") or "")
    gameweeks = [int(gw) for gw in manifest.get("gameweeks") or []]
    current_gw = recommendation.get("current_gameweek")
    team = manifest.get("team_state")
    team_state = team.get("state") if isinstance(team, dict) else None
    published_gw = team_state.get("published_gw") if isinstance(team_state, dict) else None

    if selector == LAUNCH_SELECTOR:
        if not gameweeks or gameweeks[0] != 1:
            raise ValueError("GW1 launch selector requires an actionable horizon beginning at GW1")
        if published_gw:
            raise ValueError("GW1 launch selector is invalid once a personal deadline squad exists")
        return LAUNCH_PROFILE

    if selector == INSEASON_SELECTOR:
        if not isinstance(team, dict) or team.get("configured") is not True or team.get("ok") is not True:
            raise ValueError("in-season selector requires a healthy sealed personal team state")
        if not isinstance(team_state, dict) or not published_gw:
            raise ValueError("in-season selector requires a published personal deadline squad")
        if not gameweeks:
            raise ValueError("in-season selector requires a non-empty actionable horizon")
        if current_gw is None or int(current_gw) != gameweeks[0]:
            raise ValueError("in-season selector current_gameweek does not match sealed horizon")
        if int(current_gw) <= int(published_gw):
            raise ValueError("in-season selector does not advance beyond the published deadline state")
        if not team_state.get("selling_prices_exact"):
            raise ValueError("in-season selector requires exact realised selling prices")
        selling = team_state.get("selling_prices") or {}
        squad = {int(pid) for pid in team_state.get("squad") or []}
        if len(squad) != 15 or {int(pid) for pid in selling} != squad:
            raise ValueError("in-season selector requires selling prices for the exact sealed 15")
        return INSEASON_PROFILE

    raise ValueError(f"unsupported release selector: {selector or '<missing>'}")
