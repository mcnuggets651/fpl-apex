from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Protocol

import pandas as pd
import numpy as np

from apex_fpl.replay.context import AsOfContext
from apex_fpl.replay.legality import advance_state, validate_action
from apex_fpl.replay.scoring import WeeklyScore, score_weekly_action
from apex_fpl.replay.state import ReplayState, WeeklyAction


_FORBIDDEN_DECISION_COLUMNS = {
    "assists",
    "bonus",
    "bps",
    "clean_sheets",
    "event_points",
    "goals_scored",
    "minutes",
    "red_cards",
    "saves",
    "starts",
    "total_points",
    "yellow_cards",
}


@dataclass(frozen=True)
class DecisionSurface:
    context: AsOfContext
    players: pd.DataFrame
    projections: pd.DataFrame

    def validate(self) -> None:
        leaked = sorted(
            (_FORBIDDEN_DECISION_COLUMNS & set(self.players.columns))
            | (_FORBIDDEN_DECISION_COLUMNS & set(self.projections.columns))
        )
        if leaked:
            raise ValueError("target/outcome columns crossed decision firewall: " + ", ".join(leaked))
        if "player_id" not in self.players or "player_id" not in self.projections:
            raise ValueError("decision surface requires player_id in players and projections")
        if "gw" not in self.projections:
            raise ValueError("decision projections require a gw column")
        if not self.context.sources:
            raise ValueError("historical decision surface requires attributable sources")
        projection_gws = set(pd.to_numeric(self.projections["gw"], errors="raise").astype(int))
        if self.context.gameweek not in projection_gws:
            raise ValueError("decision surface lacks projections for its target Gameweek")

    @staticmethod
    def _frame_sha256(frame: pd.DataFrame) -> str:
        columns = sorted(str(column) for column in frame.columns)
        ordering = [column for column in ("gw", "player_id") if column in columns]
        data = frame[columns].copy()
        if ordering:
            data = data.sort_values(ordering, kind="stable")
        payload = data.to_csv(index=False, lineterminator="\n", na_rep="<NA>").encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @property
    def surface_sha256(self) -> str:
        payload = {
            "manifest_sha256": self.context.manifest_sha256,
            "players_sha256": self._frame_sha256(self.players),
            "projections_sha256": self._frame_sha256(self.projections),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


class ReplayPolicy(Protocol):
    name: str

    def decide(self, state: ReplayState, surface: DecisionSurface) -> WeeklyAction: ...


@dataclass(frozen=True)
class SealedDecision:
    context_sha256: str
    surface_sha256: str
    action: WeeklyAction
    state_before_sha256: str
    state_after: ReplayState

    @property
    def decision_sha256(self) -> str:
        payload = {
            "context_sha256": self.context_sha256,
            "surface_sha256": self.surface_sha256,
            "action_sha256": self.action.action_sha256,
            "state_before_sha256": self.state_before_sha256,
            "state_after_sha256": self.state_after.state_sha256,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def to_dict(self) -> dict:
        return {
            "context_sha256": self.context_sha256,
            "surface_sha256": self.surface_sha256,
            "action": self.action.to_dict(),
            "action_sha256": self.action.action_sha256,
            "state_before_sha256": self.state_before_sha256,
            "state_after": self.state_after.to_dict(),
            "state_after_sha256": self.state_after.state_sha256,
            "decision_sha256": self.decision_sha256,
        }


@dataclass(frozen=True)
class SeasonDecisions:
    season: str
    policy: str
    decisions: tuple[SealedDecision, ...]

    def __post_init__(self) -> None:
        gameweeks = tuple(row.action.gameweek for row in self.decisions)
        if gameweeks != tuple(range(1, 39)):
            raise ValueError("season decision contract requires exactly Gameweeks 1-38")

    @property
    def final_decision_sha256(self) -> str:
        return self.decisions[-1].decision_sha256

    def to_dict(self) -> dict:
        return {
            "season": self.season,
            "policy": self.policy,
            "gameweeks": len(self.decisions),
            "final_decision_sha256": self.final_decision_sha256,
            "decisions": [row.to_dict() for row in self.decisions],
        }


@dataclass(frozen=True)
class SeasonScore:
    season: str
    policy: str
    total_points: int
    gross_points: int
    hit_cost: int
    weeks: tuple[WeeklyScore, ...]
    final_decision_sha256: str

    def to_dict(self) -> dict:
        return {
            "season": self.season,
            "policy": self.policy,
            "total_points": self.total_points,
            "gross_points": self.gross_points,
            "hit_cost": self.hit_cost,
            "final_decision_sha256": self.final_decision_sha256,
            "weeks": [row.to_dict() for row in self.weeks],
        }


@dataclass(frozen=True)
class SeasonComparison:
    candidate_policy: str
    baseline_policy: str
    realised_delta: int
    bootstrap_samples: int
    lower_90: float
    upper_90: float
    probability_candidate_better: float
    classification: str

    def to_dict(self) -> dict:
        return {
            "candidate_policy": self.candidate_policy,
            "baseline_policy": self.baseline_policy,
            "realised_delta": self.realised_delta,
            "bootstrap_samples": self.bootstrap_samples,
            "lower_90": self.lower_90,
            "upper_90": self.upper_90,
            "probability_candidate_better": self.probability_candidate_better,
            "classification": self.classification,
        }


def run_decision_season(
    *,
    initial_state: ReplayState,
    surfaces: tuple[DecisionSurface, ...],
    policy: ReplayPolicy,
    verify_determinism: bool = True,
) -> SeasonDecisions:
    """Seal 38 decisions without accepting an outcome object anywhere."""
    if tuple(surface.context.gameweek for surface in surfaces) != tuple(range(1, 39)):
        raise ValueError("replay requires one ordered decision surface for every Gameweek")
    state = initial_state
    sealed: list[SealedDecision] = []
    previous_decision: str | None = None
    for surface in surfaces:
        surface.validate()
        context = surface.context
        if context.season != state.season or context.gameweek != state.next_gameweek:
            raise ValueError("context does not reconcile with replay state")
        if (
            context.previous_decision_sha256 is not None
            and context.previous_decision_sha256 != previous_decision
        ):
            raise ValueError("context previous-decision hash breaks the replay chain")
        action = policy.decide(state, surface)
        if verify_determinism:
            repeated = policy.decide(state, surface)
            if repeated.action_sha256 != action.action_sha256:
                raise ValueError(f"policy is non-deterministic in Gameweek {context.gameweek}")
        validate_action(state, action, surface.players)
        next_state = advance_state(state, action, surface.players)
        decision = SealedDecision(
            context_sha256=context.manifest_sha256,
            surface_sha256=surface.surface_sha256,
            action=action,
            state_before_sha256=state.state_sha256,
            state_after=next_state,
        )
        sealed.append(decision)
        previous_decision = decision.decision_sha256
        state = next_state
    return SeasonDecisions(season=initial_state.season, policy=policy.name, decisions=tuple(sealed))


def score_season(
    decisions: SeasonDecisions,
    outcomes: dict[int, pd.DataFrame],
) -> SeasonScore:
    """Join outcomes only after the 38-action decision artifact is sealed."""
    if set(outcomes) != set(range(1, 39)):
        raise ValueError("realised scorer requires outcomes for exactly Gameweeks 1-38")
    weeks = tuple(
        score_weekly_action(decision.action, outcomes[decision.action.gameweek])
        for decision in decisions.decisions
    )
    return SeasonScore(
        season=decisions.season,
        policy=decisions.policy,
        total_points=sum(row.net_points for row in weeks),
        gross_points=sum(row.gross_points for row in weeks),
        hit_cost=sum(row.hit_cost for row in weeks),
        weeks=weeks,
        final_decision_sha256=decisions.final_decision_sha256,
    )


def compare_season_scores(
    candidate: SeasonScore,
    baseline: SeasonScore,
    *,
    samples: int = 5000,
    block_length: int = 4,
    seed: int = 20260811,
) -> SeasonComparison:
    """Paired circular Gameweek-block bootstrap for the decision promotion gate."""
    if candidate.season != baseline.season:
        raise ValueError("season comparison requires matching seasons")
    if len(candidate.weeks) != 38 or len(baseline.weeks) != 38:
        raise ValueError("season comparison requires 38 scored Gameweeks per policy")
    candidate_by_gw = {row.gameweek: row.net_points for row in candidate.weeks}
    baseline_by_gw = {row.gameweek: row.net_points for row in baseline.weeks}
    if set(candidate_by_gw) != set(range(1, 39)) or set(baseline_by_gw) != set(range(1, 39)):
        raise ValueError("season comparison requires exactly Gameweeks 1-38")
    differences = np.asarray(
        [candidate_by_gw[gw] - baseline_by_gw[gw] for gw in range(1, 39)],
        dtype=float,
    )
    length = int(block_length)
    if not 1 <= length <= 38:
        raise ValueError("block_length must be between 1 and 38")
    count = int(samples)
    if count < 100:
        raise ValueError("at least 100 bootstrap samples are required")
    rng = np.random.default_rng(seed)
    totals = np.empty(count, dtype=float)
    blocks_needed = int(np.ceil(38 / length))
    for sample_idx in range(count):
        starts = rng.integers(0, 38, size=blocks_needed)
        indices = np.concatenate(
            [np.arange(start, start + length) % 38 for start in starts]
        )[:38]
        totals[sample_idx] = float(differences[indices].sum())
    realised = int(differences.sum())
    lower = float(np.quantile(totals, 0.05))
    upper = float(np.quantile(totals, 0.95))
    probability = float(np.mean(totals > 0))
    if lower > 0:
        classification = "strong_pass"
    elif realised > 0 and probability >= 0.75:
        classification = "provisional_pass"
    elif realised <= 0 or probability < 0.50:
        classification = "fail"
    else:
        classification = "inconclusive"
    return SeasonComparison(
        candidate_policy=candidate.policy,
        baseline_policy=baseline.policy,
        realised_delta=realised,
        bootstrap_samples=count,
        lower_90=lower,
        upper_90=upper,
        probability_candidate_better=probability,
        classification=classification,
    )
