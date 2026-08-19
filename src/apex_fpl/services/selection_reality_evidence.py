from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from apex_fpl.services.player_identity import resolve_source_identities
from apex_fpl.services.specialist_disagreement import build_specialist_disagreement_report
from apex_fpl.services.transfer_intelligence import assess_transfer_signal


SPECIALIST_COLUMNS = [
    "player_id",
    "source_player_name",
    "source",
    "predicted_start",
    "source_url",
    "published_at",
    "retrieved_at",
    "expires_at",
]
TRANSFER_COLUMNS = [
    "player_id",
    "source_player_name",
    "source",
    "signal",
    "source_url",
    "published_at",
    "retrieved_at",
    "expires_at",
]


def _load(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    frame = pd.read_csv(path)
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(f"{path} missing governed evidence columns: {sorted(missing)}")
    return frame[columns].copy()


def _fresh(frame: pd.DataFrame, *, now: datetime | None = None) -> pd.DataFrame:
    if frame.empty:
        return frame
    current = pd.Timestamp(now or datetime.now(timezone.utc))
    current = current.tz_localize("UTC") if current.tzinfo is None else current.tz_convert("UTC")
    published = pd.to_datetime(frame["published_at"], utc=True, errors="coerce")
    retrieved = pd.to_datetime(frame["retrieved_at"], utc=True, errors="coerce")
    expires = pd.to_datetime(frame["expires_at"], utc=True, errors="coerce")
    invalid = published.isna() | retrieved.isna() | expires.isna() | (expires <= published)
    if invalid.any():
        raise ValueError(
            "governed selection-reality evidence has invalid publication/retrieval/expiry timestamps"
        )
    # Stale evidence is excluded rather than silently carried into a later deadline.
    return frame.loc[current <= expires].copy().reset_index(drop=True)


def materialize_selection_reality_evidence(
    players: pd.DataFrame,
    *,
    specialist_path: Path,
    transfer_path: Path,
    output_dir: Path,
    selected_ids: set[int] | None = None,
    optimiser_sensitive_ids: set[int] | None = None,
    now: datetime | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate and materialize diagnostic specialist/transfer evidence.

    Evidence is official-ID/name reconciled and time-bounded before it reaches the
    selected-squad reality gate. These surfaces remain diagnostic: they cannot mutate
    canonical minutes, roles, set pieces, club identity or xP.
    """
    selected_ids = {int(pid) for pid in (selected_ids or set())}
    sensitive = {int(pid) for pid in (optimiser_sensitive_ids or set())}

    specialist = _fresh(_load(specialist_path, SPECIALIST_COLUMNS), now=now)
    transfer = _fresh(_load(transfer_path, TRANSFER_COLUMNS), now=now)

    if not specialist.empty:
        specialist, result = resolve_source_identities(
            players,
            specialist,
            source="fpl_specialist_manual",
            name_columns=("source_player_name",),
            allow_name_fallback=False,
            require_identity_witness=True,
            raise_on_error=False,
        )
        if not result.ready:
            raise ValueError("specialist evidence identity failed: " + "; ".join(result.blockers[:10]))
        specialist["source"] = specialist["source"].astype(str).str.strip().str.casefold()
        specialist["predicted_start"] = (
            specialist["predicted_start"]
            .astype(str)
            .str.strip()
            .str.casefold()
            .map({"true": True, "1": True, "yes": True, "start": True, "false": False, "0": False, "no": False, "bench": False})
        )
        if specialist["predicted_start"].isna().any():
            raise ValueError("specialist predicted_start must be a boolean/start/bench value")

    specialist_report = build_specialist_disagreement_report(
        players,
        specialist,
        selected_ids=selected_ids,
        optimiser_sensitive_ids=sensitive,
    )

    transfer_rows: list[dict] = []
    if not transfer.empty:
        transfer, result = resolve_source_identities(
            players,
            transfer,
            source="transfer_specialist_manual",
            name_columns=("source_player_name",),
            allow_name_fallback=False,
            require_identity_witness=True,
            raise_on_error=False,
        )
        if not result.ready:
            raise ValueError("transfer evidence identity failed: " + "; ".join(result.blockers[:10]))
        for row in transfer.itertuples(index=False):
            pid = int(row.player_id)
            assessment = assess_transfer_signal(
                source=str(row.source),
                signal=str(row.signal),
                selected_or_sensitive=pid in selected_ids | sensitive,
            )
            transfer_rows.append(
                {
                    "player_id": pid,
                    "source": str(row.source),
                    "signal": str(row.signal),
                    "source_url": str(row.source_url),
                    "published_at": row.published_at,
                    "expires_at": row.expires_at,
                    "review_priority": assessment.review_priority,
                    "transfer_state": assessment.transfer_state,
                    "review_reason": assessment.review_reason,
                    "requires_official_confirmation": assessment.requires_official_confirmation,
                }
            )
    transfer_report = pd.DataFrame(
        transfer_rows,
        columns=[
            "player_id",
            "source",
            "signal",
            "source_url",
            "published_at",
            "expires_at",
            "review_priority",
            "transfer_state",
            "review_reason",
            "requires_official_confirmation",
        ],
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    specialist_report.to_csv(output_dir / "specialist_disagreement.csv", index=False)
    transfer_report.to_csv(output_dir / "transfer_intelligence.csv", index=False)
    return specialist_report, transfer_report
