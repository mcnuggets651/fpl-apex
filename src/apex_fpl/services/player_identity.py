from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

import pandas as pd


IDENTITY_CONTRACT = "apex-player-identity-integrity-v1"


class IdentityIntegrityError(ValueError):
    """Raised when external player evidence cannot be attached safely."""


@dataclass(frozen=True)
class IdentityResolution:
    source: str
    ready: bool
    rows: int
    exact_id_matches: int
    name_fallback_matches: int
    unresolved: int
    mismatched: int
    ambiguous: int
    coverage: float
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    report: pd.DataFrame

    def to_dict(self) -> dict:
        return {
            "contract": IDENTITY_CONTRACT,
            "source": self.source,
            "ready": self.ready,
            "rows": self.rows,
            "exact_id_matches": self.exact_id_matches,
            "name_fallback_matches": self.name_fallback_matches,
            "unresolved": self.unresolved,
            "mismatched": self.mismatched,
            "ambiguous": self.ambiguous,
            "coverage": self.coverage,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
        }


_ACTIVE_REGISTRY: pd.DataFrame | None = None


def _norm(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    return re.sub(r"[^a-z0-9]+", "", text)


def build_official_identity_registry(official: pd.DataFrame) -> pd.DataFrame:
    required = {"player_id", "web_name"}
    if not required.issubset(official.columns):
        raise IdentityIntegrityError(
            f"official FPL identity requires columns {sorted(required)}"
        )
    cols = [
        col
        for col in (
            "player_id",
            "web_name",
            "first_name",
            "second_name",
            "team",
            "team_name",
            "position",
            "price",
            "status",
        )
        if col in official.columns
    ]
    out = official[cols].drop_duplicates("player_id").copy()
    out["player_id"] = pd.to_numeric(out["player_id"], errors="raise").astype(int)
    if out["player_id"].duplicated().any():
        raise IdentityIntegrityError("official FPL identity contains duplicate player IDs")
    out["identity_web_name"] = out["web_name"].map(_norm)
    first = out.get("first_name", pd.Series("", index=out.index)).fillna("").astype(str)
    second = out.get("second_name", pd.Series("", index=out.index)).fillna("").astype(str)
    out["identity_full_name"] = (first + " " + second).map(_norm)
    return out.reset_index(drop=True)


def activate_official_identity_registry(official: pd.DataFrame | None) -> None:
    global _ACTIVE_REGISTRY
    _ACTIVE_REGISTRY = None if official is None else build_official_identity_registry(official)


def active_official_identity_registry() -> pd.DataFrame | None:
    return None if _ACTIVE_REGISTRY is None else _ACTIVE_REGISTRY.copy()


def _source_name(row: pd.Series, name_columns: tuple[str, ...]) -> str:
    for col in name_columns:
        if col in row.index and str(row.get(col) or "").strip():
            return str(row.get(col)).strip()
    first = str(row.get("first_name") or "").strip() if "first_name" in row.index else ""
    second = str(row.get("second_name") or "").strip() if "second_name" in row.index else ""
    return " ".join(part for part in (first, second) if part).strip()


def _name_matches(official_row: pd.Series, source_name: str) -> bool:
    value = _norm(source_name)
    return bool(value) and value in {
        str(official_row.get("identity_web_name") or ""),
        str(official_row.get("identity_full_name") or ""),
    }


def _context_conflicts(
    official_row: pd.Series,
    source_row: pd.Series,
    *,
    team_columns: tuple[str, ...],
    position_columns: tuple[str, ...],
) -> list[str]:
    conflicts: list[str] = []
    for col in team_columns:
        if col not in source_row.index or pd.isna(source_row.get(col)):
            continue
        source_value = str(source_row.get(col)).strip()
        if not source_value:
            continue
        if col.endswith("_id") or col == "team":
            official_value = official_row.get("team")
            try:
                if int(float(source_value)) != int(official_value):
                    conflicts.append(f"team conflict source={source_value} official={official_value}")
            except (TypeError, ValueError):
                pass
        else:
            official_value = str(official_row.get("team_name") or "")
            if _norm(source_value) and _norm(source_value) != _norm(official_value):
                conflicts.append(
                    f"team conflict source={source_value!r} official={official_value!r}"
                )
        break
    for col in position_columns:
        if col not in source_row.index or pd.isna(source_row.get(col)):
            continue
        source_value = str(source_row.get(col)).strip()
        if not source_value:
            continue
        official_value = str(official_row.get("position") or "")
        if _norm(source_value) != _norm(official_value):
            conflicts.append(
                f"position conflict source={source_value!r} official={official_value!r}"
            )
        break
    return conflicts


def resolve_source_identities(
    official: pd.DataFrame,
    source_rows: pd.DataFrame,
    *,
    source: str,
    id_col: str = "player_id",
    name_columns: tuple[str, ...] = (
        "source_player_name",
        "player_name",
        "web_name",
        "name",
    ),
    team_columns: tuple[str, ...] = ("team_id", "team", "team_name", "club"),
    position_columns: tuple[str, ...] = ("position", "element_type"),
    allow_name_fallback: bool = True,
    require_identity_witness: bool = True,
    raise_on_error: bool = True,
) -> tuple[pd.DataFrame, IdentityResolution]:
    registry = build_official_identity_registry(official)
    by_id = registry.set_index("player_id", drop=False)
    name_index: dict[str, set[int]] = {}
    for row in registry.itertuples(index=False):
        for key in {str(row.identity_web_name), str(row.identity_full_name)} - {""}:
            name_index.setdefault(key, set()).add(int(row.player_id))

    frame = source_rows.copy()
    if frame.empty:
        result = IdentityResolution(source, True, 0, 0, 0, 0, 0, 0, 1.0, tuple(), tuple(), pd.DataFrame())
        return frame, result

    report_rows: list[dict] = []
    resolved_rows: list[pd.Series] = []
    blockers: list[str] = []
    warnings: list[str] = []
    exact = fallback = unresolved = mismatched = ambiguous = 0

    for idx, row in frame.iterrows():
        raw_id = row.get(id_col) if id_col in frame.columns else None
        pid: int | None = None
        if raw_id is not None and not pd.isna(raw_id):
            try:
                pid = int(float(raw_id))
            except (TypeError, ValueError):
                pid = None
        source_name = _source_name(row, name_columns)
        witness = bool(_norm(source_name))
        status = "unresolved"
        reason = ""
        resolved_id: int | None = None

        if pid is not None:
            if pid not in by_id.index:
                unresolved += 1
                reason = f"unknown official FPL player_id={pid}"
            else:
                official_row = by_id.loc[pid]
                if require_identity_witness and not witness:
                    mismatched += 1
                    status = "mismatch"
                    reason = f"player_id={pid} has no independent identity witness"
                elif witness and not _name_matches(official_row, source_name):
                    mismatched += 1
                    status = "mismatch"
                    reason = (
                        f"player_id={pid} name conflict source={source_name!r} "
                        f"official={official_row.get('web_name')!r}"
                    )
                else:
                    conflicts = _context_conflicts(
                        official_row,
                        row,
                        team_columns=team_columns,
                        position_columns=position_columns,
                    )
                    if conflicts:
                        mismatched += 1
                        status = "mismatch"
                        reason = "; ".join(conflicts)
                    else:
                        exact += 1
                        status = "exact_id"
                        resolved_id = pid
        elif allow_name_fallback and witness:
            matches = name_index.get(_norm(source_name), set())
            if len(matches) == 1:
                resolved_id = next(iter(matches))
                official_row = by_id.loc[resolved_id]
                conflicts = _context_conflicts(
                    official_row,
                    row,
                    team_columns=team_columns,
                    position_columns=position_columns,
                )
                if conflicts:
                    mismatched += 1
                    status = "mismatch"
                    reason = "; ".join(conflicts)
                    resolved_id = None
                else:
                    fallback += 1
                    status = "name_fallback"
                    reason = f"resolved unique name {source_name!r} to official player_id={resolved_id}"
                    warnings.append(f"{source}: {reason}")
            elif len(matches) > 1:
                ambiguous += 1
                status = "ambiguous"
                reason = f"ambiguous official name fallback {source_name!r}: {sorted(matches)}"
            else:
                unresolved += 1
                reason = f"unresolved official name {source_name!r}"
        else:
            unresolved += 1
            reason = "row has neither a valid official ID nor a unique identity witness"

        if status in {"unresolved", "mismatch", "ambiguous"}:
            blockers.append(f"{source} row {idx}: {reason}")
        if resolved_id is not None:
            resolved = row.copy()
            resolved[id_col] = int(resolved_id)
            if id_col != "player_id":
                resolved["player_id"] = int(resolved_id)
            resolved_rows.append(resolved)
        report_rows.append(
            {
                "source": source,
                "row": idx,
                "input_player_id": raw_id,
                "source_player_name": source_name,
                "resolved_player_id": resolved_id,
                "status": status,
                "reason": reason,
            }
        )

    resolved = pd.DataFrame(resolved_rows, columns=frame.columns if id_col == "player_id" else None)
    if not resolved.empty and "player_id" in resolved.columns:
        resolved["player_id"] = pd.to_numeric(resolved["player_id"], errors="raise").astype(int)
    rows = len(frame)
    coverage = (exact + fallback) / rows if rows else 1.0
    result = IdentityResolution(
        source=source,
        ready=not blockers,
        rows=rows,
        exact_id_matches=exact,
        name_fallback_matches=fallback,
        unresolved=unresolved,
        mismatched=mismatched,
        ambiguous=ambiguous,
        coverage=coverage,
        blockers=tuple(dict.fromkeys(blockers)),
        warnings=tuple(dict.fromkeys(warnings)),
        report=pd.DataFrame(report_rows),
    )
    if raise_on_error and not result.ready:
        raise IdentityIntegrityError("; ".join(result.blockers[:10]))
    return resolved, result


def audit_identity_sources(
    official: pd.DataFrame,
    sources: dict[str, pd.DataFrame],
    *,
    require_identity_witness: bool = True,
) -> dict:
    results = {}
    blockers: list[str] = []
    warnings: list[str] = []
    for name, frame in sources.items():
        _, result = resolve_source_identities(
            official,
            frame,
            source=name,
            require_identity_witness=require_identity_witness,
            raise_on_error=False,
        )
        results[name] = result.to_dict()
        blockers.extend(result.blockers)
        warnings.extend(result.warnings)
    return {
        "contract": IDENTITY_CONTRACT,
        "ready": not blockers,
        "official_player_count": int(len(build_official_identity_registry(official))),
        "sources": results,
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
    }
