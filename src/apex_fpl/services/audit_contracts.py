from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from apex_fpl.services.pipeline import PipelineOutput


@dataclass(frozen=True)
class DiagnosticReadiness:
    """Readiness of a sealed surface for diagnostic model/optimiser audits.

    Diagnostic readiness is deliberately narrower than production publication
    readiness. A diagnostic must fail closed when its own immutable data surface
    is malformed, but publication-only blockers (for example a temporarily
    unhealthy corroboration feed) must not prevent us from diagnosing the model
    on the exact surface that was sealed.
    """

    ready: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    publication_safe_to_act: bool
    publication_full_apex_ready: bool
    publication_blockers: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _projection_key_blockers(
    projections: pd.DataFrame,
    pids: pd.Series,
    gws: pd.Series,
) -> list[str]:
    """Validate fixture-granular projection identity without rejecting DGWs.

    The canonical projection surface is one row per player/Official fixture, not
    necessarily one row per player/Gameweek. A Double Gameweek therefore contains
    legitimate repeated ``(player_id, gw)`` pairs. Those repeats are valid only when
    every row carries the immutable Official FPL ``fixture_id`` and the full
    ``(player_id, gw, fixture_id)`` key remains unique. Opponent/home are descriptive
    witnesses only and cannot substitute for fixture identity.
    """
    blockers: list[str] = []
    base = pd.DataFrame({"player_id": pids.astype(int), "gw": gws.astype(int)})
    repeated = base.duplicated(["player_id", "gw"], keep=False)
    if not repeated.any():
        return blockers

    if "fixture_id" not in projections.columns:
        blockers.append(
            "diagnostic projection surface has repeated player/Gameweek rows "
            "without Official fixture_id"
        )
        return blockers

    fixture_ids = pd.to_numeric(projections["fixture_id"], errors="coerce")
    if (repeated & fixture_ids.isna()).any():
        blockers.append(
            "diagnostic projection surface has repeated player/Gameweek rows with "
            "missing Official fixture_id"
        )
        return blockers

    descriptive_columns = {"opponent", "is_home"}
    missing_descriptive = sorted(descriptive_columns - set(projections.columns))
    if missing_descriptive:
        blockers.append(
            "diagnostic projection surface has repeated player/Gameweek rows "
            "without fixture witness columns: " + ", ".join(missing_descriptive)
        )
        return blockers
    opponents = pd.to_numeric(projections["opponent"], errors="coerce")
    home = projections["is_home"]
    if (repeated & (opponents.isna() | home.isna())).any():
        blockers.append(
            "diagnostic projection surface has repeated player/Gameweek rows with "
            "missing opponent/is_home fixture witness"
        )
        return blockers

    fixture_keys = base.copy()
    fixture_keys["fixture_id"] = fixture_ids
    if fixture_keys.duplicated(["player_id", "gw", "fixture_id"]).any():
        blockers.append(
            "diagnostic projection surface has duplicate player/Official-fixture rows"
        )
    return blockers


def assess_diagnostic_surface(
    output: PipelineOutput,
    *,
    projection_col: str = "xp",
) -> DiagnosticReadiness:
    blockers: list[str] = []
    warnings: list[str] = []

    players = output.players
    projections = output.projections
    gameweeks = [int(gw) for gw in output.gameweeks]

    if players.empty:
        blockers.append("diagnostic player surface is empty")
    elif "player_id" not in players.columns:
        blockers.append("diagnostic player surface has no player_id")
    else:
        player_ids = pd.to_numeric(players["player_id"], errors="coerce")
        if player_ids.isna().any():
            blockers.append("diagnostic player surface has non-numeric player IDs")
        elif player_ids.astype(int).duplicated().any():
            blockers.append("diagnostic player surface has duplicate player IDs")

    if not gameweeks:
        blockers.append("diagnostic surface has no actionable gameweeks")
    elif len(gameweeks) != len(set(gameweeks)):
        blockers.append("diagnostic surface has duplicate gameweeks")

    required_projection_columns = {"player_id", "gw", projection_col}
    missing = sorted(required_projection_columns - set(projections.columns))
    if projections.empty:
        blockers.append("diagnostic projection surface is empty")
    elif missing:
        blockers.append(
            "diagnostic projection surface missing columns: " + ", ".join(missing)
        )
    else:
        pids = pd.to_numeric(projections["player_id"], errors="coerce")
        gws = pd.to_numeric(projections["gw"], errors="coerce")
        values = pd.to_numeric(projections[projection_col], errors="coerce")
        if pids.isna().any() or gws.isna().any():
            blockers.append("diagnostic projection surface has invalid player_id/gw keys")
        else:
            keys = pd.DataFrame({"player_id": pids.astype(int), "gw": gws.astype(int)})
            blockers.extend(_projection_key_blockers(projections, pids, gws))
            if "player_id" in players.columns:
                valid_player_ids = set(
                    pd.to_numeric(players["player_id"], errors="coerce")
                    .dropna()
                    .astype(int)
                )
                unknown = sorted(set(keys["player_id"]) - valid_player_ids)
                if unknown:
                    blockers.append(
                        "diagnostic projection surface has unknown player IDs: "
                        + ", ".join(map(str, unknown[:10]))
                    )
            missing_gws = sorted(set(gameweeks) - set(keys["gw"]))
            if missing_gws:
                blockers.append(
                    "diagnostic projection surface missing gameweeks: "
                    + ", ".join(map(str, missing_gws))
                )
        finite = np.isfinite(values.to_numpy(dtype=float, na_value=np.nan))
        if not finite.all():
            blockers.append(
                f"diagnostic projection column {projection_col} contains non-finite values"
            )

    if output.integrity is not None and not output.integrity.empty:
        warnings.append(
            f"{len(output.integrity)} auxiliary identity mismatches are present; "
            "official identity remains authoritative"
        )

    publication_blockers = tuple(str(x) for x in output.safety.blockers)
    if publication_blockers:
        warnings.append(
            "production publication is blocked on this sealed surface; diagnostics "
            "remain valid only for their own contract"
        )

    return DiagnosticReadiness(
        ready=not blockers,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        publication_safe_to_act=bool(output.safety.safe_to_act),
        publication_full_apex_ready=bool(output.safety.full_apex_ready),
        publication_blockers=publication_blockers,
    )
