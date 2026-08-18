from __future__ import annotations

import pandas as pd

SPECIALIST_SOURCES = {"fantasy_football_scout", "allaboutfpl"}


def _numeric(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(default)


def build_specialist_disagreement_report(
    players: pd.DataFrame,
    specialist_predictions: pd.DataFrame,
    *,
    selected_ids: set[int] | None = None,
    optimiser_sensitive_ids: set[int] | None = None,
) -> pd.DataFrame:
    """Compare Apex minutes/start beliefs with FPL-specialist predicted-XI evidence.

    This is diagnostic only. The result never mutates canonical minutes, roles or xP.
    A high-priority review requires independent specialist agreement against Apex;
    a single specialist can only create a medium review flag for an optimiser-sensitive
    player.
    """
    selected_ids = {int(pid) for pid in (selected_ids or set())}
    optimiser_sensitive_ids = {
        int(pid) for pid in (optimiser_sensitive_ids or set())
    }

    base_cols = [
        col
        for col in [
            "player_id",
            "web_name",
            "team_name",
            "position",
            "expected_minutes",
            "start_probability",
        ]
        if col in players.columns
    ]
    base = players[base_cols].drop_duplicates("player_id").copy()
    base["player_id"] = pd.to_numeric(base["player_id"], errors="coerce").astype("Int64")
    base = base[base["player_id"].notna()].copy()
    base["player_id"] = base["player_id"].astype(int)
    base["apex_expected_minutes"] = _numeric(base, "expected_minutes")
    base["apex_start_probability"] = _numeric(base, "start_probability")

    predictions = specialist_predictions.copy()
    required = {"player_id", "source", "predicted_start"}
    if predictions.empty or not required.issubset(predictions.columns):
        base["specialist_source_count"] = 0
        base["specialist_start_votes"] = 0
        base["specialist_bench_votes"] = 0
        base["specialist_consensus"] = "none"
        base["review_priority"] = "none"
        base["review_reason"] = ""
        base["selected_or_sensitive"] = base["player_id"].isin(
            selected_ids | optimiser_sensitive_ids
        )
        return base

    predictions["player_id"] = pd.to_numeric(
        predictions["player_id"], errors="coerce"
    ).astype("Int64")
    predictions = predictions[predictions["player_id"].notna()].copy()
    predictions["player_id"] = predictions["player_id"].astype(int)
    predictions["source"] = predictions["source"].astype(str).str.strip().str.casefold()
    predictions = predictions[predictions["source"].isin(SPECIALIST_SOURCES)].copy()
    predictions["predicted_start"] = predictions["predicted_start"].astype(bool)
    predictions = predictions.drop_duplicates(["player_id", "source"], keep="last")

    grouped = predictions.groupby("player_id")
    summary = grouped.agg(
        specialist_source_count=("source", "nunique"),
        specialist_start_votes=("predicted_start", "sum"),
    ).reset_index()
    summary["specialist_bench_votes"] = (
        summary["specialist_source_count"] - summary["specialist_start_votes"]
    )

    def consensus(row) -> str:
        count = int(row.specialist_source_count)
        starts = int(row.specialist_start_votes)
        benches = int(row.specialist_bench_votes)
        if count >= 2 and starts == count:
            return "start"
        if count >= 2 and benches == count:
            return "bench"
        if count:
            return "split"
        return "none"

    summary["specialist_consensus"] = summary.apply(consensus, axis=1)
    out = base.merge(summary, on="player_id", how="left")
    for col in [
        "specialist_source_count",
        "specialist_start_votes",
        "specialist_bench_votes",
    ]:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)
    out["specialist_consensus"] = out["specialist_consensus"].fillna("none")
    out["selected_or_sensitive"] = out["player_id"].isin(
        selected_ids | optimiser_sensitive_ids
    )

    priorities: list[str] = []
    reasons: list[str] = []
    for row in out.itertuples(index=False):
        apex_start = float(row.apex_start_probability)
        consensus_value = str(row.specialist_consensus)
        count = int(row.specialist_source_count)
        sensitive = bool(row.selected_or_sensitive)

        if consensus_value == "bench" and apex_start >= 0.75:
            priorities.append("high")
            reasons.append(
                "FFS and AllAboutFPL agree on bench/non-start while Apex carries a high start probability"
            )
        elif consensus_value == "start" and apex_start <= 0.40:
            priorities.append("high")
            reasons.append(
                "FFS and AllAboutFPL agree on a start while Apex carries a low start probability"
            )
        elif count == 1 and sensitive:
            priorities.append("medium")
            reasons.append(
                "single FPL-specialist prediction conflicts or requires review for an optimiser-sensitive player"
            )
        elif consensus_value == "split" and sensitive:
            priorities.append("medium")
            reasons.append(
                "FPL-specialist predicted-XI sources disagree for an optimiser-sensitive player"
            )
        else:
            priorities.append("none")
            reasons.append("")

    out["review_priority"] = priorities
    out["review_reason"] = reasons
    return out
