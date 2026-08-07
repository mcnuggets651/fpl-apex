from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class ProjectionScenarios:
    """Correlated player/Gameweek projection scenarios.

    ``values`` has shape ``(scenario, player, gameweek)`` and represents plausible
    *forecast surfaces*, not simulated final FPL match scores. The distinction is
    important: the purpose is to stress the squad decision against uncertainty in
    minutes, team strength and attacking/defensive expectation rather than pretend
    that the exact distribution of every football event is known.
    """

    player_ids: np.ndarray
    gameweeks: np.ndarray
    values: np.ndarray
    seed: int
    model_version: str = "apex-correlated-forecast-v1"

    @property
    def n_scenarios(self) -> int:
        return int(self.values.shape[0])

    def summary_frame(self) -> pd.DataFrame:
        rows: list[dict] = []
        for i, pid in enumerate(self.player_ids):
            for t, gw in enumerate(self.gameweeks):
                v = self.values[:, i, t]
                rows.append(
                    {
                        "player_id": int(pid),
                        "gw": int(gw),
                        "scenario_mean_xp": float(np.mean(v)),
                        "scenario_sd_xp": float(np.std(v, ddof=0)),
                        "scenario_p10_xp": float(np.quantile(v, 0.10)),
                        "scenario_p50_xp": float(np.quantile(v, 0.50)),
                        "scenario_p90_xp": float(np.quantile(v, 0.90)),
                    }
                )
        return pd.DataFrame(rows)


def _numeric(frame: pd.DataFrame, column: str, default: float = 0.0) -> np.ndarray:
    if column not in frame.columns:
        return np.full(len(frame), float(default), dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(default).to_numpy(float)


def generate_projection_scenarios(
    players: pd.DataFrame,
    projections: pd.DataFrame,
    gameweeks: list[int],
    *,
    n_scenarios: int = 256,
    seed: int = 20260807,
    marginal_sd_scale: float = 1.0,
) -> ProjectionScenarios:
    """Generate covariance-aware forecast scenarios around the Apex ensemble.

    Correlation is introduced through shared Gameweek and team attack/defence
    shocks. A high attack shock for one club is also a negative clean-sheet shock
    for the opponent, so attacker-vs-opposing-defender exposure is not treated as
    independent. Remaining uncertainty is idiosyncratic.

    The marginal volatility comes from ``projection_sd`` and is converted to a
    positive log-normal perturbation. This preserves the ensemble mean in
    expectation before finite-sample noise while keeping scenario xP non-negative.

    The correlation coefficients are transparent priors, not fitted 2026/27
    parameters. They should be walk-forward calibrated once enough deadline data
    exists; until then the layer is a robustness stress model rather than a claim
    of exact football covariance.
    """
    gws = np.asarray([int(gw) for gw in gameweeks], dtype=int)
    if len(gws) == 0:
        raise ValueError("at least one gameweek is required")
    if n_scenarios < 16:
        raise ValueError("n_scenarios must be at least 16")

    player_table = players.drop_duplicates("player_id")[["player_id", "team"]].copy()
    player_table["player_id"] = pd.to_numeric(
        player_table["player_id"], errors="raise"
    ).astype(int)
    player_table["team"] = pd.to_numeric(player_table["team"], errors="raise").astype(int)
    pids = np.sort(player_table["player_id"].unique())
    pid_index = {int(pid): i for i, pid in enumerate(pids)}
    gw_index = {int(gw): i for i, gw in enumerate(gws)}

    d = projections[projections["gw"].isin(gws)].copy()
    if d.empty:
        raise ValueError("projection table has no rows for requested gameweeks")
    d["player_id"] = pd.to_numeric(d["player_id"], errors="raise").astype(int)
    d["gw"] = pd.to_numeric(d["gw"], errors="raise").astype(int)
    d = d.merge(player_table, on="player_id", how="left", validate="many_to_one")
    if d["team"].isna().any():
        missing = sorted(d.loc[d["team"].isna(), "player_id"].unique())[:10]
        raise ValueError(f"scenario rows contain players without official team IDs: {missing}")
    d["team"] = d["team"].astype(int)

    base = _numeric(d, "xp", np.nan)
    if np.isnan(base).all():
        base = _numeric(d, "risk_adjusted_xp", np.nan)
    if np.isnan(base).all():
        base = _numeric(d, "apex_xp", 0.0)
    base = np.nan_to_num(base, nan=0.0, posinf=0.0, neginf=0.0)
    base = np.maximum(base, 0.0)

    sd = _numeric(d, "projection_sd", np.nan)
    fallback_sd = np.sqrt(np.maximum(0.55 * base, 0.35))
    sd = np.where(np.isfinite(sd) & (sd > 0), sd, fallback_sd)
    sd = np.maximum(sd * float(marginal_sd_scale), 0.05)

    attack_component = (
        _numeric(d, "xp_attack", 0.0)
        + _numeric(d, "xp_set_piece_prior", 0.0)
        + 0.45 * _numeric(d, "xp_bonus_prior", 0.0)
    )
    defence_component = (
        _numeric(d, "xp_clean_sheet", 0.0)
        + _numeric(d, "xp_defensive_contribution", 0.0)
        + _numeric(d, "xp_saves", 0.0)
        + 0.20 * _numeric(d, "xp_bonus_prior", 0.0)
    )
    apex_total = np.maximum(_numeric(d, "apex_xp", 0.0), 1e-6)
    attack_share = np.clip(attack_component / apex_total, 0.0, 1.0)
    defence_share = np.clip(defence_component / apex_total, 0.0, 1.0)
    share_sum = attack_share + defence_share
    too_large = share_sum > 0.92
    if np.any(too_large):
        scale = 0.92 / np.maximum(share_sum[too_large], 1e-9)
        attack_share[too_large] *= scale
        defence_share[too_large] *= scale

    opponent_raw = _numeric(d, "opponent", np.nan)
    opponents = np.where(np.isfinite(opponent_raw), opponent_raw, -1).astype(int)
    teams = d["team"].to_numpy(int)
    row_gw = d["gw"].to_numpy(int)

    unique_teams = np.sort(player_table["team"].unique())
    team_index = {int(team): i for i, team in enumerate(unique_teams)}
    rng = np.random.default_rng(int(seed))
    s_count = int(n_scenarios)
    t_count = len(gws)
    club_count = len(unique_teams)

    global_gw = rng.standard_normal((s_count, t_count))
    attack_shock = rng.standard_normal((s_count, t_count, club_count))
    defence_shock = rng.standard_normal((s_count, t_count, club_count))
    idio = rng.standard_normal((s_count, len(d)))

    row_values = np.zeros((s_count, len(d)), dtype=float)
    for r in range(len(d)):
        gw_i = gw_index[int(row_gw[r])]
        team_i = team_index[int(teams[r])]
        opp_i = team_index.get(int(opponents[r]))
        a_share = float(attack_share[r])
        d_share = float(defence_share[r])

        c_global = 0.10
        c_team_attack = 0.72 * a_share
        c_opp_defence = -0.28 * a_share
        c_team_defence = 0.70 * d_share
        c_opp_attack = -0.35 * d_share
        c_idio = 0.58

        z = c_global * global_gw[:, gw_i]
        z = z + c_team_attack * attack_shock[:, gw_i, team_i]
        z = z + c_team_defence * defence_shock[:, gw_i, team_i]
        variance = c_global**2 + c_team_attack**2 + c_team_defence**2 + c_idio**2
        if opp_i is not None:
            z = z + c_opp_defence * defence_shock[:, gw_i, opp_i]
            z = z + c_opp_attack * attack_shock[:, gw_i, opp_i]
            variance += c_opp_defence**2 + c_opp_attack**2
        z = z + c_idio * idio[:, r]
        z = z / max(float(np.sqrt(variance)), 1e-9)

        mean = float(base[r])
        if mean <= 1e-9:
            continue
        relative_sd = min(float(sd[r]) / mean, 1.75)
        sigma = float(np.sqrt(np.log1p(relative_sd**2)))
        row_values[:, r] = mean * np.exp(sigma * z - 0.5 * sigma**2)

    values = np.zeros((s_count, len(pids), len(gws)), dtype=float)
    for r, row in enumerate(d.itertuples(index=False)):
        p_i = pid_index[int(row.player_id)]
        g_i = gw_index[int(row.gw)]
        values[:, p_i, g_i] += row_values[:, r]

    return ProjectionScenarios(
        player_ids=pids.astype(int),
        gameweeks=gws,
        values=values,
        seed=int(seed),
    )
