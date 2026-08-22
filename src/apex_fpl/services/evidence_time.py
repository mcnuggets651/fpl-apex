from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd


MAX_FUTURE_CLOCK_SKEW = timedelta(minutes=5)


def current_evidence_rows(
    frame: pd.DataFrame,
    *,
    observed_col: str,
    expires_col: str,
    retrieved_col: str | None = None,
    now: datetime | None = None,
    label: str = "governed evidence",
    strict: bool = True,
) -> pd.DataFrame:
    """Validate evidence chronology and return rows valid at ``now``.

    Evidence may only influence a decision when its observation/publication time is
    known, its optional retrieval time is not earlier than that observation, its
    expiry is later than the observation, and neither observation nor retrieval is
    materially future-dated. Expired evidence is valid historical evidence but is
    excluded from the current decision. Malformed chronology is a contract error in
    strict mode and is dropped in permissive repository-default mode.
    """
    if frame.empty:
        return frame.copy()
    required = {observed_col, expires_col}
    if retrieved_col is not None:
        required.add(retrieved_col)
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label} missing timestamp columns: {missing}")

    current = pd.Timestamp(now or datetime.now(timezone.utc))
    current = (
        current.tz_localize("UTC")
        if current.tzinfo is None
        else current.tz_convert("UTC")
    )
    future_limit = current + pd.Timedelta(MAX_FUTURE_CLOCK_SKEW)
    observed = pd.to_datetime(frame[observed_col], utc=True, errors="coerce")
    expires = pd.to_datetime(frame[expires_col], utc=True, errors="coerce")
    invalid = observed.isna() | expires.isna() | (expires <= observed) | (observed > future_limit)

    if retrieved_col is not None:
        retrieved = pd.to_datetime(frame[retrieved_col], utc=True, errors="coerce")
        invalid |= (
            retrieved.isna()
            | (retrieved < observed)
            | (retrieved > future_limit)
        )

    if invalid.any():
        if strict:
            raise ValueError(f"{label} has invalid timestamp chronology")
        frame = frame.loc[~invalid].copy()
        expires = expires.loc[~invalid]

    if frame.empty:
        return frame.reset_index(drop=True)
    current_mask = current <= expires
    return frame.loc[current_mask].copy().reset_index(drop=True)
