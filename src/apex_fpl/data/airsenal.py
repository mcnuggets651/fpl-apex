from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ALIASES = {
    "player_id": ("player_id", "element", "fpl_id", "player_code"),
    "gw": ("gw", "gameweek", "event"),
    "xp": ("xp", "xP", "expected_points", "prediction", "predicted_points"),
    "xmins": ("expected_minutes", "xMins", "xmins", "minutes"),
    "confidence": ("confidence",),
}
METADATA_COLUMNS = ("generated_at", "source_version", "prediction_tag")
SUPPORT_COLUMN = "source_supported"
SUPPORT_REASON_COLUMN = "support_reason"


def _find(columns, field: str) -> str | None:
    return next((name for name in ALIASES[field] if name in columns), None)


def _metadata(df: pd.DataFrame, index: pd.Index) -> pd.DataFrame:
    result = pd.DataFrame(index=index)
    for col in METADATA_COLUMNS:
        if col in df.columns:
            result[col] = df[col].values
        else:
            result[col] = pd.NA
    return result


def _support_flags(df: pd.DataFrame, index: pd.Index) -> tuple[pd.Series, pd.Series]:
    """Return explicit source-support metadata with strict boolean parsing.

    Older/manual exports without this metadata remain supported for compatibility.
    The production worker emits it on every row, allowing structural upstream
    abstentions to remain distinguishable from a genuine zero-point opinion.
    """
    if SUPPORT_COLUMN not in df.columns:
        return (
            pd.Series(True, index=index, dtype=bool),
            pd.Series("", index=index, dtype="string"),
        )
    raw = df[SUPPORT_COLUMN]
    if raw.dtype == bool:
        supported = raw.astype(bool)
    else:
        normalised = raw.astype(str).str.strip().str.casefold()
        valid = normalised.isin({"true", "false", "1", "0", "yes", "no"})
        if not bool(valid.all()):
            bad = sorted(set(raw.loc[~valid].astype(str)))[:10]
            raise ValueError(f"AIrsenal export has invalid source_supported values: {bad}")
        supported = normalised.isin({"true", "1", "yes"})
    reason = (
        df[SUPPORT_REASON_COLUMN].fillna("").astype("string")
        if SUPPORT_REASON_COLUMN in df.columns
        else pd.Series("", index=index, dtype="string")
    )
    missing_reason = ~supported.to_numpy(bool) & reason.astype(str).str.strip().eq("").to_numpy(bool)
    if bool(np.any(missing_reason)):
        raise ValueError("AIrsenal unsupported rows require support_reason provenance")
    return pd.Series(supported.to_numpy(bool), index=index), pd.Series(reason.values, index=index)


class AIrsenalProjectionAdapter:
    """Read a genuine AIrsenal export without coupling Apex to its DB schema.

    The canonical contract is one row per official FPL ``player_id`` / Gameweek.
    AIrsenal's own internal ``player.player_id`` must never enter this adapter; the
    exporter joins to ``player.fpl_api_id`` first.

    Raw xP and usable xP are deliberately separate. A production worker may mark an
    upstream row unsupported when the row exists only as structural filler. Such raw
    values remain auditable in ``airsenal_raw_xp`` while ``airsenal_xp`` becomes
    missing so the ensemble uses its explicit governed fallback instead of treating
    filler zero as an independent expert opinion.
    """

    def __init__(self, path: str | None):
        self.path = Path(path).expanduser() if path else None

    def available(self) -> bool:
        return bool(self.path and self.path.exists())

    def load(self, valid_ids: set[int] | None = None) -> pd.DataFrame:
        cols = [
            "player_id",
            "gw",
            "airsenal_xp",
            "airsenal_raw_xp",
            "airsenal_source_supported",
            "airsenal_support_reason",
            "airsenal_xmins",
            "airsenal_confidence",
            *METADATA_COLUMNS,
        ]
        if not self.available():
            return pd.DataFrame(columns=cols)

        df = pd.read_csv(self.path)
        pid_col, gw_col, xp_col = (_find(df.columns, x) for x in ("player_id", "gw", "xp"))
        if pid_col and gw_col and xp_col:
            raw_xp = pd.to_numeric(df[xp_col], errors="raise").astype(float)
            supported, reason = _support_flags(df, df.index)
            out = pd.DataFrame(
                {
                    "player_id": pd.to_numeric(df[pid_col], errors="raise").astype(int),
                    "gw": pd.to_numeric(df[gw_col], errors="raise").astype(int),
                    "airsenal_raw_xp": raw_xp,
                    "airsenal_source_supported": supported.astype(bool),
                    "airsenal_support_reason": reason.astype("string"),
                }
            )
            out["airsenal_xp"] = raw_xp.where(out["airsenal_source_supported"], np.nan)
            xm = _find(df.columns, "xmins")
            conf = _find(df.columns, "confidence")
            out["airsenal_xmins"] = (
                pd.to_numeric(df[xm], errors="coerce") if xm else pd.Series(pd.NA, index=df.index)
            )
            out["airsenal_confidence"] = (
                pd.to_numeric(df[conf], errors="coerce")
                if conf
                else pd.Series(pd.NA, index=df.index)
            )
            out = pd.concat([out, _metadata(df, out.index)], axis=1)
        else:
            gw_cols = [c for c in df.columns if str(c).upper().startswith("GW")]
            if not pid_col or not gw_cols:
                raise ValueError(
                    "AIrsenal CSV must contain official player ID plus (gameweek, expected points) "
                    "or wide GW* columns"
                )
            id_vars = [pid_col, *[c for c in METADATA_COLUMNS if c in df.columns]]
            long = df.melt(
                id_vars=id_vars,
                value_vars=gw_cols,
                var_name="gw",
                value_name="airsenal_raw_xp",
            )
            long["player_id"] = pd.to_numeric(long[pid_col], errors="raise").astype(int)
            long["gw"] = (
                long["gw"].astype(str).str.upper().str.replace("GW", "", regex=False).astype(int)
            )
            long["airsenal_raw_xp"] = pd.to_numeric(long["airsenal_raw_xp"], errors="raise")
            out = long[["player_id", "gw", "airsenal_raw_xp"]].copy()
            out["airsenal_source_supported"] = True
            out["airsenal_support_reason"] = ""
            out["airsenal_xp"] = out["airsenal_raw_xp"]
            out["airsenal_xmins"] = pd.NA
            out["airsenal_confidence"] = pd.NA
            for col in METADATA_COLUMNS:
                out[col] = long[col] if col in long.columns else pd.NA

        out["airsenal_raw_xp"] = pd.to_numeric(out["airsenal_raw_xp"], errors="coerce")
        out["airsenal_xp"] = pd.to_numeric(out["airsenal_xp"], errors="coerce")
        out["airsenal_xmins"] = pd.to_numeric(out["airsenal_xmins"], errors="coerce")
        out["airsenal_confidence"] = pd.to_numeric(out["airsenal_confidence"], errors="coerce")
        if valid_ids is not None:
            unknown = sorted(set(out["player_id"]) - set(valid_ids))
            if unknown:
                raise ValueError(
                    "AIrsenal export contains unknown official FPL IDs. This commonly means "
                    f"AIrsenal internal IDs were exported by mistake: {unknown[:10]}"
                )
        if (out["gw"] <= 0).any():
            raise ValueError("AIrsenal export contains invalid gameweek")
        if out.duplicated(["player_id", "gw"]).any():
            duplicate = out.loc[out.duplicated(["player_id", "gw"], keep=False), ["player_id", "gw"]]
            sample = duplicate.drop_duplicates().head(10).to_dict("records")
            raise ValueError(
                "AIrsenal export must be aggregated to one row per official player/Gameweek; "
                f"duplicates include {sample}"
            )
        return out.sort_values(["gw", "player_id"]).reset_index(drop=True)


def validate_airsenal_forecast(
    forecast: pd.DataFrame,
    valid_ids: set[int],
    gameweeks: list[int],
    *,
    expected_source_version: str = "",
    max_age_hours: float = 36.0,
    min_player_coverage: float = 1.0,
) -> tuple[bool, str]:
    """Validate that an AIrsenal file is genuine, current and horizon-complete.

    Completeness is assessed on the raw export. Explicitly unsupported rows are
    allowed only when their raw value is still finite and provenance says why the
    upstream abstained; those rows are not counted as usable expert opinions.
    """
    if forecast.empty:
        return False, "genuine projection export not configured"

    unknown = sorted(set(forecast["player_id"].astype(int)) - set(valid_ids))
    if unknown:
        return False, f"unknown official FPL IDs: {unknown[:10]}"

    requested = set(map(int, gameweeks))
    covered = set(pd.to_numeric(forecast["gw"], errors="coerce").dropna().astype(int)) & requested
    missing = sorted(requested - covered)
    if missing:
        return False, f"missing requested Gameweeks: {missing}"

    raw_col = "airsenal_raw_xp" if "airsenal_raw_xp" in forecast.columns else "airsenal_xp"
    raw_xp = pd.to_numeric(forecast[raw_col], errors="coerce")
    if raw_xp.isna().any() or not np.isfinite(raw_xp).all():
        return False, "raw expected-points surface contains non-finite values"
    if (raw_xp < 0).any() or (raw_xp > 40).any():
        sample = forecast.loc[(raw_xp < 0) | (raw_xp > 40), ["player_id", "gw", raw_col]]
        return False, f"expected-points values outside [0, 40]: {sample.head(5).to_dict('records')}"

    if "airsenal_source_supported" in forecast.columns:
        support = forecast["airsenal_source_supported"]
        if support.isna().any():
            return False, "source-supported metadata is incomplete"
        support = support.astype(bool)
        usable = pd.to_numeric(forecast["airsenal_xp"], errors="coerce")
        if usable.loc[support].isna().any() or not np.isfinite(usable.loc[support]).all():
            return False, "supported AIrsenal rows contain non-finite usable xP"
        if usable.loc[~support].notna().any():
            return False, "unsupported AIrsenal rows must abstain from usable xP"
        reason = forecast.get(
            "airsenal_support_reason", pd.Series("", index=forecast.index)
        ).fillna("").astype(str).str.strip()
        if reason.loc[~support].eq("").any():
            return False, "unsupported AIrsenal rows are missing support_reason provenance"
    else:
        support = pd.Series(True, index=forecast.index, dtype=bool)

    if "airsenal_xmins" in forecast and forecast["airsenal_xmins"].notna().any():
        xmins = pd.to_numeric(forecast["airsenal_xmins"], errors="coerce")
        invalid_xmins = xmins.notna() & (~np.isfinite(xmins) | (xmins < 0) | (xmins > 180))
        if invalid_xmins.any():
            return False, "expected-minutes values outside [0, 180]"
    if "airsenal_confidence" in forecast and forecast["airsenal_confidence"].notna().any():
        confidence = pd.to_numeric(forecast["airsenal_confidence"], errors="coerce")
        invalid_confidence = confidence.notna() & (
            ~np.isfinite(confidence) | ~confidence.between(0, 1, inclusive="both")
        )
        if invalid_confidence.any():
            return False, "confidence values outside [0, 1]"

    min_players = max(1, int(len(valid_ids) * min_player_coverage))
    requested_rows = forecast[forecast["gw"].isin(gameweeks)]
    coverage = requested_rows.groupby("gw")["player_id"].nunique()
    thin = {int(gw): int(count) for gw, count in coverage.items() if int(count) < min_players}
    if thin:
        return False, f"insufficient official-player coverage; expected >= {min_players} per GW, got {thin}"

    if "generated_at" not in forecast or forecast["generated_at"].isna().all():
        return False, "missing generated_at provenance; re-export with scripts/export_airsenal.py"
    generated = pd.to_datetime(requested_rows["generated_at"], utc=True, errors="coerce")
    if generated.isna().any():
        return False, "invalid generated_at provenance"
    generations = generated.drop_duplicates()
    if len(generations) != 1:
        return False, (
            "export mixes multiple AIrsenal generations across required rows: "
            f"{[stamp.isoformat() for stamp in generations[:5]]}"
        )
    newest = generations.iloc[0]
    now = datetime.now(timezone.utc)
    age_hours = (now - newest.to_pydatetime()).total_seconds() / 3600
    if age_hours < -0.25:
        return False, f"forecast timestamp is {abs(age_hours):.1f}h in the future"
    if age_hours > max_age_hours:
        return False, f"AIrsenal forecast is stale ({age_hours:.1f}h old; max {max_age_hours:.1f}h)"

    versions = {
        str(value).strip()
        for value in requested_rows.get("source_version", pd.Series(dtype=str)).dropna().tolist()
        if str(value).strip()
    }
    if expected_source_version:
        if not versions:
            return False, "missing source_version provenance; pinned AIrsenal commit cannot be verified"
        if versions != {expected_source_version}:
            return False, (
                f"AIrsenal version mismatch: expected {expected_source_version}, "
                f"found {sorted(versions)}"
            )

    tags = {
        str(value).strip()
        for value in requested_rows.get("prediction_tag", pd.Series(dtype=str)).dropna().tolist()
        if str(value).strip()
    }
    if not tags:
        return False, "missing prediction_tag provenance"
    if len(tags) != 1:
        return False, f"export mixes multiple AIrsenal prediction tags: {sorted(tags)}"

    counts = {int(gw): int(count) for gw, count in coverage.items()}
    support_rows = support.loc[requested_rows.index]
    semantic_abstentions = int((~support_rows).sum())
    supported_players = int(
        requested_rows.loc[support_rows, "player_id"].nunique()
    ) if bool(support_rows.any()) else 0
    return True, (
        f"{len(forecast)} rows; raw player coverage={counts}; "
        f"semantic supported players={supported_players}/{len(valid_ids)}; "
        f"semantic abstention rows={semantic_abstentions}; age={max(age_hours, 0):.1f}h; "
        f"tag={next(iter(tags))}"
    )
