from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import tempfile
from pathlib import Path
from typing import Any

PUBLIC_OUTCOME_PREFIX = "apex-v2/outcome"
PRIVATE_MANAGER_PREFIX = "apex-v2/private"
PRIVATE_DQ_PREFIX = "apex-v2/private-decision-quality"
DQ_ASSETS = frozenset({"decision_quality.json", "decision_quality_attestation.json"})


def canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_path(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _int_map(raw: Any) -> dict[int, float]:
    if not isinstance(raw, dict):
        return {}
    output: dict[int, float] = {}
    for key, value in raw.items():
        try:
            output[int(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return output


def _int_list(raw: Any) -> list[int]:
    if not isinstance(raw, (list, tuple)):
        return []
    output: list[int] = []
    for value in raw:
        try:
            output.append(int(value))
        except (TypeError, ValueError):
            continue
    return output


def _official_players(private_attempt: dict[str, Any]) -> dict[int, dict[str, Any]]:
    rows = (((private_attempt.get("canonical_forecast") or {}).get("official") or {}).get("players") or [])
    players: dict[int, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            players[int(row["element_id"])] = row
        except (KeyError, TypeError, ValueError):
            continue
    return players


def _position_counts(ids: tuple[int, ...], players: dict[int, dict[str, Any]]) -> dict[str, int]:
    counts = {"GK": 0, "DEF": 0, "MID": 0, "FWD": 0}
    for pid in ids:
        position = str((players.get(pid) or {}).get("position") or "")
        if position not in counts:
            raise RuntimeError(f"missing/invalid Official position for element {pid}")
        counts[position] += 1
    return counts


def legal_xi(ids: tuple[int, ...], players: dict[int, dict[str, Any]]) -> bool:
    if len(ids) != 11 or len(set(ids)) != 11:
        return False
    counts = _position_counts(ids, players)
    return (
        counts["GK"] == 1
        and 3 <= counts["DEF"] <= 5
        and 2 <= counts["MID"] <= 5
        and 1 <= counts["FWD"] <= 3
    )


def best_legal_xi(squad_ids: list[int], actual_points: dict[int, float], players: dict[int, dict[str, Any]]) -> tuple[list[int], float]:
    if len(squad_ids) != 15 or len(set(squad_ids)) != 15:
        raise RuntimeError("decision quality requires an exact 15-player final squad")
    missing = [pid for pid in squad_ids if pid not in players]
    if missing:
        raise RuntimeError("Official player catalog does not cover final squad")
    best_ids: tuple[int, ...] | None = None
    best_points: float | None = None
    for combo in itertools.combinations(squad_ids, 11):
        if not legal_xi(combo, players):
            continue
        points = float(sum(actual_points.get(pid, 0.0) for pid in combo))
        if best_points is None or points > best_points or (points == best_points and combo < (best_ids or combo)):
            best_ids = combo
            best_points = points
    if best_ids is None or best_points is None:
        raise RuntimeError("final squad contains no legal FPL XI")
    return list(best_ids), best_points


def _h1_expected_minutes(private_attempt: dict[str, Any]) -> dict[int, float]:
    forecast = private_attempt.get("canonical_forecast") or {}
    gameweek = int(private_attempt.get("target_gameweek") or 0)
    serving = forecast.get("serving_provider_by_horizon") or {}
    champion = str(serving.get("1", serving.get(1, "")) or "")
    output: dict[int, float] = {}
    for row in forecast.get("rows") or []:
        if not isinstance(row, dict):
            continue
        try:
            if int(row.get("gameweek", -1)) != gameweek or int(row.get("horizon", -1)) != 1:
                continue
            if champion and str(row.get("serving_provider_id") or "") != champion:
                continue
            if row.get("expected_minutes") is None:
                continue
            output[int(row["element_id"])] = float(row["expected_minutes"])
        except (KeyError, TypeError, ValueError):
            continue
    return output


def build_decision_quality(
    private_attempt: dict[str, Any],
    outcome: dict[str, Any],
    *,
    source_private_sha256: str,
    source_outcome_sha256: str,
    control_plane_sha: str,
) -> dict[str, Any]:
    public_id = str(private_attempt.get("public_attempt_id") or "")
    if not public_id or str(outcome.get("public_attempt_id") or "") != public_id:
        raise RuntimeError("decision-quality public/private identity mismatch")
    gameweek = int(private_attempt.get("target_gameweek") or 0)
    if gameweek <= 0 or int(outcome.get("gameweek") or -1) != gameweek:
        raise RuntimeError("decision-quality Gameweek mismatch")
    system = private_attempt.get("system_decision")
    if not isinstance(system, dict):
        raise RuntimeError("decision-quality source has no system decision")

    actual = _int_map(outcome.get("actual_points"))
    minutes = _int_map(outcome.get("actual_minutes"))
    if not actual or not minutes:
        raise RuntimeError("decision-quality outcome has no scoreable actuals")
    squad_ids = _int_list(system.get("squad_ids"))
    xi_ids = _int_list(system.get("xi_ids"))
    bench_ids = _int_list(system.get("bench_order"))
    if len(xi_ids) != 11 or len(bench_ids) != 4:
        raise RuntimeError("decision-quality requires exact XI and four-player bench")
    if set(xi_ids) | set(bench_ids) != set(squad_ids):
        raise RuntimeError("decision-quality XI/bench do not partition final squad")
    players = _official_players(private_attempt)
    if not legal_xi(tuple(xi_ids), players):
        raise RuntimeError("sealed selected XI is not a legal formation")

    best_ids, best_points = best_legal_xi(squad_ids, actual, players)
    selected_points = float(sum(actual.get(pid, 0.0) for pid in xi_ids))
    bench_points = float(sum(actual.get(pid, 0.0) for pid in bench_ids))

    captain_id = int(system.get("captain_id"))
    vice_id = int(system.get("vice_captain_id"))
    if captain_id not in squad_ids or vice_id not in squad_ids:
        raise RuntimeError("captain or vice-captain is outside final squad")
    if minutes.get(captain_id, 0.0) > 0:
        effective_captain = captain_id
    elif minutes.get(vice_id, 0.0) > 0:
        effective_captain = vice_id
    else:
        effective_captain = None
    effective_bonus = float(actual.get(effective_captain, 0.0)) if effective_captain is not None else 0.0
    available_xi = [pid for pid in xi_ids if minutes.get(pid, 0.0) > 0]
    best_captain = max(available_xi, key=lambda pid: (actual.get(pid, 0.0), -pid)) if available_xi else None
    best_bonus = float(actual.get(best_captain, 0.0)) if best_captain is not None else 0.0

    transfers_in = _int_list(system.get("transfers_in"))
    transfers_out = _int_list(system.get("transfers_out"))
    incoming_points = float(sum(actual.get(pid, 0.0) for pid in transfers_in))
    outgoing_points = float(sum(actual.get(pid, 0.0) for pid in transfers_out))
    transfer_delta = incoming_points - outgoing_points if len(transfers_in) == len(transfers_out) else None

    expected_minutes = _h1_expected_minutes(private_attempt)
    minute_rows = [pid for pid in squad_ids if pid in expected_minutes and pid in minutes]
    minute_mae = (
        float(sum(abs(expected_minutes[pid] - minutes[pid]) for pid in minute_rows) / len(minute_rows))
        if minute_rows
        else None
    )
    team_state = private_attempt.get("team_state") or {}

    return {
        "schema_version": 1,
        "contract": "APEX_V2_PRIVATE_DECISION_QUALITY_V1",
        "production_influence": "NONE",
        "serving_authorized": False,
        "promotion_authority": False,
        "source": {
            "season": private_attempt.get("season"),
            "gameweek": gameweek,
            "public_attempt_id": public_id,
            "private_attempt_id": private_attempt.get("private_attempt_id"),
            "private_manager_sha256": source_private_sha256,
            "outcomes_sha256": source_outcome_sha256,
            "official_live_hash": outcome.get("official_live_hash"),
            "canonical_projection_sha256": (private_attempt.get("canonical_forecast") or {}).get("canonical_projection_sha256"),
            "control_plane_sha": control_plane_sha,
        },
        "captaincy": {
            "sealed_captain_id": captain_id,
            "sealed_vice_captain_id": vice_id,
            "effective_captain_id": effective_captain,
            "effective_captain_bonus_points": effective_bonus,
            "best_realized_captain_id_within_sealed_xi": best_captain,
            "best_realized_captain_bonus_points_within_sealed_xi": best_bonus,
            "captain_bonus_realized_regret": max(0.0, best_bonus - effective_bonus),
        },
        "lineup": {
            "selected_xi_points_pre_autosub": selected_points,
            "best_legal_xi_points_within_final_15": best_points,
            "starting_xi_realized_regret_pre_autosub": max(0.0, best_points - selected_points),
            "best_legal_xi_ids_within_final_15": best_ids,
            "bench_realized_points": bench_points,
            "zero_minute_selected_starters": [pid for pid in xi_ids if minutes.get(pid, 0.0) <= 0],
            "bench_players_with_minutes": [pid for pid in bench_ids if minutes.get(pid, 0.0) > 0],
        },
        "transfers": {
            "free_transfers_before": team_state.get("free_transfers"),
            "rolled_or_held": not transfers_in and not transfers_out,
            "transfers_in": transfers_in,
            "transfers_out": transfers_out,
            "same_gameweek_incoming_points": incoming_points,
            "same_gameweek_outgoing_points": outgoing_points,
            "same_gameweek_transferred_player_points_delta_vs_hold": transfer_delta,
            "transfer_hits_recorded": int(system.get("transfer_hits") or 0),
            "hit_cost_interpreted": False,
        },
        "minutes": {
            "final_squad_expected_minutes_rows": len(minute_rows),
            "final_squad_expected_minutes_coverage": len(minute_rows) / len(squad_ids) if squad_ids else 0.0,
            "final_squad_expected_minutes_mae": minute_mae,
        },
        "notes": [
            "All metrics are retrospective observational diagnostics over a prospectively sealed decision and immutable post-Gameweek outcome.",
            "Captain regret is conditional on the sealed XI; lineup regret is separately measured as pre-autosub hindsight within the owned final 15.",
            "Transferred-player delta is same-Gameweek incoming minus outgoing realized points only; it is not total team regret and future value/hit cost are deliberately not inferred here.",
            "These diagnostics cannot alter serving-provider authority or production decisions.",
        ],
    }


def _find_release(releases: list[dict[str, Any]], tag: str) -> dict[str, Any] | None:
    return next((row for row in releases if str(row.get("tag_name")) == tag and not row.get("draft")), None)


def publish_completed(*, season: str, control_plane_sha: str) -> list[str]:
    from apex.runtime.publication import PRIVATE_RELEASE_ASSETS_V1
    from apex.runtime.releases import GitHubReleaseStore, download_release_asset, release_asset_map

    public_repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    public_token = os.environ.get("GITHUB_TOKEN", "").strip()
    private_repo = os.environ.get("APEX_PRIVATE_GITHUB_REPOSITORY", "").strip()
    private_token = os.environ.get("APEX_PRIVATE_GITHUB_TOKEN", "").strip()
    if not all((public_repo, public_token, private_repo, private_token)):
        raise RuntimeError("decision-quality scoring requires complete public/private store credentials")
    if public_repo == private_repo:
        raise RuntimeError("decision-quality private repository must be separate from public Apex")

    public_store = GitHubReleaseStore(public_repo, public_token)
    private_store = GitHubReleaseStore(private_repo, private_token)
    private_store.assert_repository_policy(require_private=True, require_immutable=True, require_initialized=True)
    public_releases = public_store.list_releases()
    private_releases = private_store.list_releases()
    private_by_tag = {str(row.get("tag_name")): row for row in private_releases if not row.get("draft")}
    published: list[str] = []
    outcome_prefix = f"{PUBLIC_OUTCOME_PREFIX}/{season}/"
    outcomes = [
        row for row in public_releases
        if str(row.get("tag_name") or "").startswith(outcome_prefix) and not row.get("draft")
    ]
    for outcome_release in sorted(outcomes, key=lambda row: str(row.get("published_at") or "")):
        if not bool(outcome_release.get("immutable", False)):
            raise RuntimeError("decision-quality outcome source is not immutable")
        run_id = str(outcome_release["tag_name"]).split(outcome_prefix, 1)[1]
        manager_tag = f"{PRIVATE_MANAGER_PREFIX}/{season}/{run_id}"
        dq_tag = f"{PRIVATE_DQ_PREFIX}/{season}/{run_id}"
        manager_release = private_by_tag.get(manager_tag)
        if manager_release is None:
            continue
        existing = private_by_tag.get(dq_tag)
        if existing is not None:
            if not bool(existing.get("immutable", False)):
                raise RuntimeError("existing decision-quality release is not immutable")
            if frozenset(release_asset_map(existing)) != DQ_ASSETS:
                raise RuntimeError("existing decision-quality release asset contract mismatch")
            continue
        if not bool(manager_release.get("immutable", False)):
            raise RuntimeError("decision-quality private source is not immutable")
        if frozenset(release_asset_map(outcome_release)) != frozenset({"outcomes.json"}):
            raise RuntimeError("outcome release asset contract mismatch")
        if frozenset(release_asset_map(manager_release)) != PRIVATE_RELEASE_ASSETS_V1:
            raise RuntimeError("private manager source asset contract mismatch")

        with tempfile.TemporaryDirectory(prefix="apex-decision-quality-") as tmp:
            root = Path(tmp)
            outcome_path = download_release_asset(public_store, outcome_release, "outcomes.json", root / "outcomes.json")
            manager_path = download_release_asset(private_store, manager_release, "private_manager_attempt.json", root / "private_manager_attempt.json")
            manager_attestation_path = download_release_asset(private_store, manager_release, "private_attestation.json", root / "private_attestation.json")
            outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
            private_attempt = json.loads(manager_path.read_text(encoding="utf-8"))
            manager_attestation = json.loads(manager_attestation_path.read_text(encoding="utf-8"))
            manager_sha = sha256_path(manager_path)
            if manager_attestation.get("scope") != "PRIVATE_MANAGER":
                raise RuntimeError("decision-quality private attestation scope mismatch")
            if manager_attestation.get("assets") != {"private_manager_attempt.json": manager_sha}:
                raise RuntimeError("decision-quality private attestation hash mismatch")
            if str(manager_attestation.get("public_attempt_id") or "") != str(outcome.get("public_attempt_id") or ""):
                raise RuntimeError("decision-quality source identity mismatch")
            dq = build_decision_quality(
                private_attempt,
                outcome,
                source_private_sha256=manager_sha,
                source_outcome_sha256=sha256_path(outcome_path),
                control_plane_sha=control_plane_sha,
            )
            dq_path = root / "decision_quality.json"
            dq_path.write_bytes(canonical_bytes(dq) + b"\n")
            attestation = {
                "schema_version": 1,
                "contract": "APEX_V2_PRIVATE_DECISION_QUALITY_ATTESTATION_V1",
                "source_public_attempt_id": dq["source"]["public_attempt_id"],
                "source_private_manager_sha256": dq["source"]["private_manager_sha256"],
                "source_outcomes_sha256": dq["source"]["outcomes_sha256"],
                "assets": {"decision_quality.json": sha256_path(dq_path)},
            }
            attestation_path = root / "decision_quality_attestation.json"
            attestation_path.write_bytes(canonical_bytes(attestation) + b"\n")
            ref = private_store.create_once(
                dq_tag,
                {"decision_quality.json": dq_path, "decision_quality_attestation.json": attestation_path},
                target_commitish=None,
                name=f"Apex V2 private decision quality {season} GW{dq['source']['gameweek']} {run_id}",
                body="Owner-private retrospective diagnostics over sealed Apex decisions. Non-serving; no promotion authority.",
            )
            if not ref.immutable:
                raise RuntimeError("decision-quality release is not immutable")
            published.append(dq_tag)
    return published


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", default="2026-2027")
    parser.add_argument("--control-plane-sha", required=True)
    args = parser.parse_args()
    tags = publish_completed(season=args.season, control_plane_sha=args.control_plane_sha)
    print(json.dumps({"published": tags, "production_influence": "NONE", "promotion_authority": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
