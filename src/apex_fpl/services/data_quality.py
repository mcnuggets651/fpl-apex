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

# FPL can append new players between enrichment refreshes. Core is valuable context,
# but is not a canonical-xP dependency while the production champion is independent of
# it. We still validate and disclose every gap; severity follows actual dependency.
MAX_CORE_REGISTRATION_LAG_PLAYERS = 5
MIN_CORE_REGISTRATION_LAG_COVERAGE = 0.99


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


def _core_ids(core: pd.DataFrame) -> set[int]:
    if core.empty or "player_id" not in core.columns:
        return set()
    return set(pd.to_numeric(core["player_id"], errors="coerce").dropna().astype(int))


def _core_coverage(core: pd.DataFrame, valid_ids: set[int]) -> float:
    if not valid_ids:
        return 0.0
    ids = _core_ids(core)
    return len(ids & valid_ids) / len(valid_ids)


def _projection_pairs_complete(
    projections: pd.DataFrame,
    player_ids: set[int],
    gameweeks: list[int],
) -> bool:
    """Return whether every requested player/GW has a finite canonical xP value.

    Projection confidence is deliberately not part of this hard contract. A provider
    may expose no calibrated confidence surface; manufacturing one merely to pass a
    coverage gate would be worse than reporting confidence as unavailable.
    """
    if not player_ids:
        return True
    if not {"player_id", "gw", "xp"}.issubset(projections.columns):
        return False
    rows = projections.copy()
    rows["player_id"] = pd.to_numeric(rows["player_id"], errors="coerce")
    rows["gw"] = pd.to_numeric(rows["gw"], errors="coerce")
    rows["xp"] = pd.to_numeric(rows["xp"], errors="coerce")
    rows = rows[
        rows["player_id"].isin(player_ids)
        & rows["gw"].isin(gameweeks)
        & rows["xp"].notna()
        & np.isfinite(rows["xp"])
        & rows["xp"].ge(0)
    ]
    pairs = set(
        (int(pid), int(gw))
        for pid, gw in rows[["player_id", "gw"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    expected = {(pid, int(gw)) for pid in player_ids for gw in gameweeks}
    return pairs == expected


def _core_playerstats_check(
    core: pd.DataFrame,
    valid_ids: set[int],
    projections: pd.DataFrame,
    gameweeks: list[int],
    minimum_core_coverage: float,
) -> QualityCheck:
    """Validate Core coverage with one bounded append-only registration fallback.

    The target remains 100%. A fallback is allowed only when all missing Official IDs
    are a tiny trailing block above the largest Core ID and those players already have
    a complete canonical projection surface. This distinguishes the normal race where
    Official FPL has just registered new players from arbitrary data loss inside Core.
    No missing Core statistic is fabricated.
    """
    core_ids = _core_ids(core)
    coverage = _core_coverage(core, valid_ids)
    if coverage >= minimum_core_coverage:
        return QualityCheck(
            "fpl_core_playerstats",
            "pass",
            False,
            f"official-player coverage={coverage:.1%}",
            coverage,
            minimum_core_coverage,
        )

    missing = sorted(valid_ids - core_ids)
    max_core_id = max(core_ids) if core_ids else None
    trailing_only = bool(
        missing
        and max_core_id is not None
        and all(player_id > max_core_id for player_id in missing)
    )
    bounded = (
        len(missing) <= MAX_CORE_REGISTRATION_LAG_PLAYERS
        and coverage >= MIN_CORE_REGISTRATION_LAG_COVERAGE
    )
    projected = _projection_pairs_complete(projections, set(missing), gameweeks)
    if trailing_only and bounded and projected:
        return QualityCheck(
            "fpl_core_playerstats",
            "fallback",
            False,
            (
                f"official-player coverage={coverage:.1%}; bounded trailing Official "
                f"registration lag missing_ids={missing}; Core values remain absent "
                "(not fabricated) and every missing player has a complete canonical "
                "projection surface"
            ),
            coverage,
            minimum_core_coverage,
        )

    reasons: list[str] = []
    if not trailing_only:
        reasons.append("missing IDs are not an append-only trailing registration block")
    if not bounded:
        reasons.append(
            f"gap exceeds bounded lag policy (max {MAX_CORE_REGISTRATION_LAG_PLAYERS} "
            f"players and minimum {MIN_CORE_REGISTRATION_LAG_COVERAGE:.1%} coverage)"
        )
    if not projected:
        reasons.append("missing Core players lack complete canonical projections")
    detail = f"official-player coverage={coverage:.1%}"
    if missing:
        detail += f"; missing_ids={missing[:20]}"
    if reasons:
        detail += "; " + "; ".join(reasons)
    return QualityCheck(
        "fpl_core_playerstats",
        "fail",
        False,
        detail,
        coverage,
        minimum_core_coverage,
    )


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
    advanced_cols = [
        col
        for col in ("xg", "xa", "defensive_contributions")
        if col in friendlies.columns
    ]
    event_cols = [
        col
        for col in (
            "goals",
            "assists",
            "total_shots",
            "shots_on_target",
            "chances_created",
            "touches_opposition_box",
        )
        if col in friendlies.columns
    ]
    advanced_coverage = (
        float(
            friendlies[advanced_cols]
            .apply(pd.to_numeric, errors="coerce")
            .notna()
            .any(axis=1)
            .mean()
        )
        if advanced_cols
        else 0.0
    )
    event_coverage = (
        float(
            friendlies[event_cols]
            .apply(pd.to_numeric, errors="coerce")
            .notna()
            .any(axis=1)
            .mean()
        )
        if event_cols
        else 0.0
    )
    status = "pass" if advanced_coverage >= 0.80 else "warning"
    return QualityCheck(
        "preseason_evidence",
        status,
        False,
        (
            f"{len(friendlies)} player-match rows; advanced xG/xA/defcon observation "
            f"coverage={advanced_coverage:.1%}; reliable goals/assists/shots/chances "
            f"evidence coverage={event_coverage:.1%}; event evidence is preserved but "
            "does not affect attacking xP until its fallback challenger is historically validated"
        ),
        advanced_coverage,
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
            False,
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
            False,
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
        False,
        f"{len(unique)}/{expected} official team-fixture sides have finite goal/clean-sheet priors",
        coverage,
        1.0,
    )


def _projection_surface_check(
    projections: pd.DataFrame,
    valid_ids: set[int],
    gameweeks: list[int],
) -> QualityCheck:
    """Hard production coverage is finite canonical xP, not synthetic confidence."""
    expected = len(valid_ids) * len(gameweeks)
    required = {"player_id", "gw", "xp"}
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
    xp = pd.to_numeric(rows["xp"], errors="coerce")
    valid = xp.notna() & np.isfinite(xp) & xp.ge(0)
    pairs = rows.loc[valid, ["player_id", "gw"]].drop_duplicates()
    coverage = min(len(pairs) / expected, 1.0) if expected else 0.0

    detail = f"{len(pairs)}/{expected} official player/Gameweek pairs have finite canonical xP"
    if "projection_confidence" in rows:
        confidence = pd.to_numeric(rows["projection_confidence"], errors="coerce")
        calibrated = confidence.notna() & np.isfinite(confidence) & confidence.between(0, 1, inclusive="both")
        detail += f"; calibrated confidence coverage={float(calibrated.mean()) if len(rows) else 0.0:.1%}"

    return QualityCheck(
        "player_projection_surface",
        "pass" if coverage >= 1.0 else "fail",
        True,
        detail,
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
    minimum_core_coverage: float = 1.0,
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
                False,
                f"{strength_detail}; internal fixture-strength enrichment unavailable; canonical champion xP remains independent",
                0.0,
                1.0,
            )
        )

    checks.append(
        _core_playerstats_check(
            core,
            valid_ids,
            projections,
            gameweeks,
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
        and check.status in {"fail", "warning", "unavailable", "fallback"}
    )
    return DataQualityAssessment(not blockers, blockers, warnings, tuple(checks))
