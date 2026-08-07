from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from apex_fpl.data.official import OfficialSnapshot


OFFICIAL_STRENGTH_COLUMNS = (
    "strength_attack_home",
    "strength_defence_home",
    "strength_attack_away",
    "strength_defence_away",
)


@dataclass(frozen=True)
class QualityCheck:
    name: str
    status: str
    required: bool
    detail: str
    coverage: float | None = None
    minimum_coverage: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DataQualityAssessment:
    ready: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    checks: tuple[QualityCheck, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "checks": [check.to_dict() for check in self.checks],
        }


def official_strength_is_usable(teams: pd.DataFrame) -> tuple[bool, str]:
    missing = [col for col in OFFICIAL_STRENGTH_COLUMNS if col not in teams.columns]
    if missing:
        return False, f"missing columns: {missing}"
    values = teams[list(OFFICIAL_STRENGTH_COLUMNS)].apply(
        pd.to_numeric, errors="coerce"
    )
    if values.isna().any().any():
        bad = int(values.isna().any(axis=1).sum())
        return False, f"{bad}/{len(values)} teams contain non-numeric strength values"
    if (values <= 0).any().any():
        bad = int((values <= 0).any(axis=1).sum())
        return False, f"{bad}/{len(values)} teams contain zero/non-positive strength values"
    spread = values.max(axis=0) - values.min(axis=0)
    if not bool((spread > 0).all()):
        flat = spread[spread <= 0].index.tolist()
        return False, f"strength fields are constant and non-informative: {flat}"
    return True, f"{len(values)}/{len(values)} teams have positive, varying strength fields"


def _core_coverage(core: pd.DataFrame, valid_ids: set[int]) -> float:
    if core.empty or "player_id" not in core.columns or not valid_ids:
        return 0.0
    ids = set(pd.to_numeric(core["player_id"], errors="coerce").dropna().astype(int))
    return len(ids & valid_ids) / len(valid_ids)


def _preseason_check(friendlies: pd.DataFrame) -> QualityCheck:
    if friendlies.empty:
        return QualityCheck(
            "preseason_evidence",
            "unavailable",
            False,
            "no preseason player-match rows; historical priors remain active",
            0.0,
            None,
        )
    identity = {"player_id", "match_id", "minutes_played"}
    missing = sorted(identity - set(friendlies.columns))
    if missing:
        return QualityCheck(
            "preseason_evidence",
            "fail",
            False,
            f"preseason rows missing identity/minutes columns: {missing}",
        )
    stat_cols = [
        col
        for col in ("xg", "xa", "defensive_contributions")
        if col in friendlies.columns
    ]
    if not stat_cols:
        return QualityCheck(
            "preseason_evidence",
            "warning",
            False,
            f"{len(friendlies)} player-match rows contain minutes but no return statistics",
            0.0,
            None,
        )
    observed = friendlies[stat_cols].apply(pd.to_numeric, errors="coerce").notna()
    coverage = float(observed.any(axis=1).mean())
    status = "pass" if coverage >= 0.80 else "warning"
    return QualityCheck(
        "preseason_evidence",
        status,
        False,
        f"{len(friendlies)} player-match rows; return-stat observation coverage={coverage:.1%}",
        coverage,
        0.80,
    )


def _fixture_surface_check(
    official: OfficialSnapshot,
    fixture_surface: pd.DataFrame,
    gameweeks: list[int],
) -> QualityCheck:
    relevant = official.fixtures[official.fixtures["event"].isin(gameweeks)].copy()
    expected = len(relevant) * 2
    if expected <= 0:
        return QualityCheck(
            "fixture_projection_surface",
            "fail",
            True,
            f"official FPL has no fixtures in requested Gameweeks {gameweeks}",
            0.0,
            1.0,
        )
    required = {"gw", "team", "opponent", "expected_team_goals", "clean_sheet_prob"}
    if fixture_surface.empty or not required.issubset(fixture_surface.columns):
        missing = sorted(required - set(fixture_surface.columns))
        return QualityCheck(
            "fixture_projection_surface",
            "fail",
            True,
            f"fixture model missing required rows/columns: {missing}",
            0.0,
            1.0,
        )
    rows = fixture_surface[fixture_surface["gw"].isin(gameweeks)].copy()
    numeric = rows[["expected_team_goals", "clean_sheet_prob"]].apply(
        pd.to_numeric, errors="coerce"
    )
    valid = (
        numeric.notna().all(axis=1)
        & np.isfinite(numeric).all(axis=1)
        & numeric["expected_team_goals"].gt(0)
        & numeric["clean_sheet_prob"].between(0, 1, inclusive="both")
    )
    unique = rows.loc[valid, ["gw", "team", "opponent"]].drop_duplicates()
    coverage = min(len(unique) / expected, 1.0)
    return QualityCheck(
        "fixture_projection_surface",
        "pass" if coverage >= 1.0 else "fail",
        True,
        f"{len(unique)}/{expected} official team-fixture sides have finite goal/clean-sheet priors",
        coverage,
        1.0,
    )


def _projection_surface_check(
    projections: pd.DataFrame,
    valid_ids: set[int],
    gameweeks: list[int],
) -> QualityCheck:
    expected = len(valid_ids) * len(gameweeks)
    required = {"player_id", "gw", "xp", "projection_confidence"}
    if projections.empty or not required.issubset(projections.columns):
        missing = sorted(required - set(projections.columns))
        return QualityCheck(
            "player_projection_surface",
            "fail",
            True,
            f"projection surface missing required rows/columns: {missing}",
            0.0,
            1.0,
        )
    rows = projections[projections["gw"].isin(gameweeks)].copy()
    numeric = rows[["xp", "projection_confidence"]].apply(pd.to_numeric, errors="coerce")
    valid = (
        numeric.notna().all(axis=1)
        & np.isfinite(numeric).all(axis=1)
        & numeric["xp"].ge(0)
        & numeric["projection_confidence"].between(0, 1, inclusive="both")
    )
    pairs = rows.loc[valid, ["player_id", "gw"]].drop_duplicates()
    coverage = min(len(pairs) / expected, 1.0) if expected else 0.0
    return QualityCheck(
        "player_projection_surface",
        "pass" if coverage >= 1.0 else "fail",
        True,
        f"{len(pairs)}/{expected} official player/Gameweek pairs have finite projections",
        coverage,
        1.0,
    )


def assess_data_quality(
    official: OfficialSnapshot,
    core: pd.DataFrame,
    friendlies: pd.DataFrame,
    fixture_surface: pd.DataFrame,
    projections: pd.DataFrame,
    gameweeks: list[int],
    *,
    fixture_fallback_ok: bool,
    minimum_core_coverage: float = 0.95,
) -> DataQualityAssessment:
    checks: list[QualityCheck] = []
    valid_ids = set(official.players["player_id"].astype(int))

    strength_ok, strength_detail = official_strength_is_usable(official.teams)
    if strength_ok:
        checks.append(
            QualityCheck("official_team_strength", "pass", False, strength_detail, 1.0, 1.0)
        )
    elif fixture_fallback_ok:
        checks.append(
            QualityCheck(
                "official_team_strength",
                "fallback",
                False,
                f"{strength_detail}; validated fallback fixture model is active",
                0.0,
                1.0,
            )
        )
    else:
        checks.append(
            QualityCheck(
                "official_team_strength",
                "fail",
                True,
                f"{strength_detail}; no validated fallback fixture model is active",
                0.0,
                1.0,
            )
        )

    core_coverage = _core_coverage(core, valid_ids)
    checks.append(
        QualityCheck(
            "fpl_core_playerstats",
            "pass" if core_coverage >= minimum_core_coverage else "fail",
            True,
            f"official-player coverage={core_coverage:.1%}",
            core_coverage,
            minimum_core_coverage,
        )
    )
    checks.append(_preseason_check(friendlies))
    checks.append(_fixture_surface_check(official, fixture_surface, gameweeks))
    checks.append(_projection_surface_check(projections, valid_ids, gameweeks))

    blockers = tuple(
        f"data quality failed: {check.name}: {check.detail}"
        for check in checks
        if check.required and check.status == "fail"
    )
    warnings = tuple(
        f"data quality {check.status}: {check.name}: {check.detail}"
        for check in checks
        if not (check.required and check.status == "fail")
        and check.status in {"warning", "unavailable", "fallback"}
    )
    return DataQualityAssessment(not blockers, blockers, warnings, tuple(checks))
