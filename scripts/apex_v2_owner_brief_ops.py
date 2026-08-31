from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

PRESENTATION_PREFIX = "apex-v2/private-presentation"
PUBLIC_FINAL_PREFIX = "apex-v2/final"
PRIVATE_MANAGER_PREFIX = "apex-v2/private"
PRESENTATION_ASSETS = frozenset({"owner_brief.json", "owner_brief.md", "owner_brief_attestation.json"})


def canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def _int_list(values: Any) -> list[int]:
    if not isinstance(values, (list, tuple)):
        return []
    output: list[int] = []
    for value in values:
        try:
            output.append(int(value))
        except (TypeError, ValueError):
            continue
    return output


def _player_map(private_attempt: dict[str, Any]) -> dict[int, dict[str, Any]]:
    official = ((private_attempt.get("canonical_forecast") or {}).get("official") or {})
    rows = official.get("players") or []
    output: dict[int, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            output[int(row["element_id"])] = row
        except (KeyError, TypeError, ValueError):
            continue
    return output


def _player_label(player_id: int | None, players: dict[int, dict[str, Any]]) -> dict[str, Any] | None:
    if player_id is None:
        return None
    pid = int(player_id)
    row = players.get(pid)
    if not isinstance(row, dict):
        raise RuntimeError(f"Official player catalog does not cover sealed element {pid}")
    name = str(row.get("web_name") or "").strip()
    position = str(row.get("position") or "").strip()
    if not name or position not in {"GK", "DEF", "MID", "FWD"}:
        raise RuntimeError(f"Official identity is incomplete for sealed element {pid}")
    return {
        "element_id": pid,
        "name": name,
        "position": position,
        "team_id": row.get("team_id"),
        "price_tenths": row.get("price_tenths"),
    }


def _label_many(ids: Any, players: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    return [label for pid in _int_list(ids) if (label := _player_label(pid, players)) is not None]


def _h2_h3_plan(
    private_attempt: dict[str, Any],
    players: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    raw = private_attempt.get("transfer_plan") or []
    if not isinstance(raw, list):
        return []
    selected: dict[int, dict[str, Any]] = {}
    for row in raw:
        if not isinstance(row, dict):
            continue
        try:
            horizon = int(row.get("horizon", -1))
        except (TypeError, ValueError):
            continue
        if horizon not in {2, 3} or horizon in selected:
            continue
        selected[horizon] = {
            "horizon": horizon,
            "gameweek": row.get("gameweek"),
            "transfers_in": _label_many(row.get("transfers_in"), players),
            "transfers_out": _label_many(row.get("transfers_out"), players),
            "bank_tenths": row.get("bank_tenths"),
            "free_transfers": row.get("free_transfers"),
            "hits": row.get("hits"),
            "submitted_ev": row.get("submitted_ev"),
        }
    return [selected[horizon] for horizon in (2, 3) if horizon in selected]


def _deadline(private_attempt: dict[str, Any]) -> str | None:
    forecast = private_attempt.get("canonical_forecast") or {}
    official = forecast.get("official") or {}
    deadlines = official.get("deadlines") or {}
    gameweek = int(private_attempt.get("target_gameweek") or 0)
    value = deadlines.get(str(gameweek), deadlines.get(gameweek)) if isinstance(deadlines, dict) else None
    return str(value) if value else None


def build_owner_brief(
    private_attempt: dict[str, Any],
    public_attempt: dict[str, Any],
    governance: dict[str, Any],
    *,
    source_private_sha256: str,
    control_plane_sha: str,
) -> dict[str, Any]:
    if private_attempt.get("schema_version") not in {1, 2}:
        raise RuntimeError("unsupported private manager attempt schema")
    public_id = str(public_attempt.get("public_attempt_id") or "")
    if not public_id or str(private_attempt.get("public_attempt_id") or "") != public_id:
        raise RuntimeError("public/private attempt identity mismatch")
    if int(private_attempt.get("target_gameweek") or -1) != int(public_attempt.get("target_gameweek") or -2):
        raise RuntimeError("public/private target Gameweek mismatch")

    manager_actionability = public_attempt.get("manager_actionability") or governance.get("manager_actionability") or {}
    certification = public_attempt.get("certification") or governance.get("certification") or {}
    system = private_attempt.get("system_decision")
    if not isinstance(system, dict):
        system = {}
    personalized = bool(manager_actionability.get("personalized_actionable"))
    certified = bool(certification.get("actionable"))
    actionable = bool(personalized and certified and system)
    status = "ACTIONABLE" if actionable else "NOT_ACTIONABLE"

    players = _player_map(private_attempt)
    captain = _player_label(system.get("captain_id"), players) if system else None
    vice = _player_label(system.get("vice_captain_id"), players) if system else None
    transfers_in = _label_many(system.get("transfers_in"), players) if system else []
    transfers_out = _label_many(system.get("transfers_out"), players) if system else []
    team_state = private_attempt.get("team_state") or {}
    decision = {
        "decision_mode": system.get("decision_mode") if system else None,
        "transfer_action": "TRANSFER" if transfers_in or transfers_out else "ROLL_OR_HOLD",
        "transfers_in": transfers_in,
        "transfers_out": transfers_out,
        "xi": _label_many(system.get("xi_ids"), players) if system else [],
        "captain": captain,
        "vice_captain": vice,
        "bench": _label_many(system.get("bench_order"), players) if system else [],
        "transfer_hits_recorded": int(system.get("transfer_hits") or 0) if system else 0,
        "objective": system.get("objective") if system else None,
        "decision_horizon": int(system.get("horizon") or 0) if system else 0,
    }
    team = {
        "entry_id": team_state.get("entry_id"),
        "bank_tenths": team_state.get("bank_tenths"),
        "free_transfers": team_state.get("free_transfers"),
        "active_chip": team_state.get("active_chip"),
        "exact_transfer_state_verified": bool(manager_actionability.get("exact_transfer_state_verified")),
        "current_editable_team_verified": bool(manager_actionability.get("current_editable_team_verified")),
    }
    return {
        "schema_version": 1,
        "contract": "APEX_V2_OWNER_BRIEF_READ_ONLY_V1",
        "production_influence": "NONE",
        "serving_authorized": False,
        "source": {
            "season": private_attempt.get("season"),
            "target_gameweek": int(private_attempt.get("target_gameweek") or 0),
            "public_attempt_id": public_id,
            "private_attempt_id": private_attempt.get("private_attempt_id"),
            "private_manager_sha256": source_private_sha256,
            "canonical_forecast_sha256": private_attempt.get("canonical_forecast_sha256"),
            "frozen_at": public_attempt.get("frozen_at"),
            "deadline_time": _deadline(private_attempt),
            "frozen_engine_sha": public_attempt.get("code_sha"),
            "control_plane_sha": control_plane_sha,
        },
        "status": status,
        "certification": {
            "state": certification.get("state"),
            "actionable": certified,
            "reasons": certification.get("reasons") or [],
            "warnings": certification.get("warnings") or [],
            "valid_until": certification.get("valid_until"),
        },
        "manager_actionability": manager_actionability,
        "team": team,
        "decision": decision,
        "h2_h3_plan": _h2_h3_plan(private_attempt, players),
        "serving_provider_by_horizon": (
            (private_attempt.get("canonical_forecast") or {}).get("serving_provider_by_horizon") or {}
        ),
        "guardrails": {
            "recomputed_xp": False,
            "reranked_players": False,
            "altered_transfer_decision": False,
            "challenger_blending": False,
            "private_only": True,
        },
    }


def render_markdown(brief: dict[str, Any]) -> str:
    source = brief["source"]
    decision = brief["decision"]
    team = brief["team"]
    cert = brief["certification"]

    def names(rows: list[dict[str, Any]]) -> str:
        return ", ".join(str(row.get("name")) for row in rows) or "None"

    transfer_text = "Roll / hold"
    if decision["transfers_in"] or decision["transfers_out"]:
        transfer_text = f"OUT: {names(decision['transfers_out'])} → IN: {names(decision['transfers_in'])}"
    captain = (decision.get("captain") or {}).get("name") or "None"
    vice = (decision.get("vice_captain") or {}).get("name") or "None"
    warnings = cert.get("warnings") or []
    lines = [
        f"# Apex V2 Owner Brief — GW{source['target_gameweek']}",
        "",
        f"**Status:** {brief['status']}",
        f"**Transfer:** {transfer_text}",
        f"**Captain:** {captain}",
        f"**Vice-captain:** {vice}",
        f"**XI:** {names(decision['xi'])}",
        f"**Bench:** {names(decision['bench'])}",
        f"**Bank:** {team.get('bank_tenths')} tenths",
        f"**Free transfers:** {team.get('free_transfers')}",
        f"**Deadline:** {source.get('deadline_time') or 'Unknown'}",
        f"**Frozen at:** {source.get('frozen_at') or 'Unknown'}",
        "",
        "## Warnings",
    ]
    lines.extend([f"- {warning}" for warning in warnings] or ["- None"])
    plan = brief.get("h2_h3_plan") or []
    lines.extend(["", "## H2-H3 sealed plan"])
    if plan:
        for row in plan:
            transfer_text = "Roll / hold"
            if row.get("transfers_in") or row.get("transfers_out"):
                transfer_text = (
                    f"OUT: {names(row.get('transfers_out') or [])} → "
                    f"IN: {names(row.get('transfers_in') or [])}"
                )
            lines.append(
                f"- H{row.get('horizon')} / GW{row.get('gameweek')}: {transfer_text}; "
                f"bank={row.get('bank_tenths')} tenths; "
                f"FT={row.get('free_transfers')}; hits={row.get('hits')}"
            )
    else:
        lines.append("- No H2-H3 transfer-plan entry was sealed for this attempt.")
    lines.extend(
        [
            "",
            "## Safety contract",
            "This is a read-only rendering of the sealed Apex V2 decision. It does not recompute xP, rerank players, blend challengers, or alter the transfer decision.",
            "",
        ]
    )
    return "\n".join(lines)


def _find_release(releases: list[dict[str, Any]], tag: str) -> dict[str, Any] | None:
    return next((row for row in releases if str(row.get("tag_name")) == tag and not row.get("draft")), None)


def _latest_run_id(private_releases: list[dict[str, Any]], season: str) -> str:
    prefix = f"{PRIVATE_MANAGER_PREFIX}/{season}/"
    candidates = [
        row for row in private_releases
        if str(row.get("tag_name") or "").startswith(prefix) and not row.get("draft")
    ]
    if not candidates:
        raise RuntimeError("no immutable private manager attempt is available")
    latest = max(candidates, key=lambda row: str(row.get("published_at") or row.get("updated_at") or ""))
    return str(latest["tag_name"]).split(prefix, 1)[1]


def run_publish(*, season: str, run_id: str, control_plane_sha: str) -> str:
    from apex.runtime.publication import PRIVATE_RELEASE_ASSETS_V1, PUBLIC_RELEASE_ASSETS_V1, verify_public_attestation
    from apex.runtime.releases import GitHubReleaseStore, download_release_asset, release_asset_map

    public_repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    public_token = os.environ.get("GITHUB_TOKEN", "").strip()
    private_repo = os.environ.get("APEX_PRIVATE_GITHUB_REPOSITORY", "").strip()
    private_token = os.environ.get("APEX_PRIVATE_GITHUB_TOKEN", "").strip()
    if not all((public_repo, public_token, private_repo, private_token)):
        raise RuntimeError("owner brief requires complete public/private release-store credentials")
    if private_repo == public_repo:
        raise RuntimeError("owner brief private repository must be separate from public Apex")

    public_store = GitHubReleaseStore(public_repo, public_token)
    private_store = GitHubReleaseStore(private_repo, private_token)
    private_store.assert_repository_policy(require_private=True, require_immutable=True, require_initialized=True)
    public_releases = public_store.list_releases()
    private_releases = private_store.list_releases()
    source_run = run_id.strip() or _latest_run_id(private_releases, season)
    public_tag = f"{PUBLIC_FINAL_PREFIX}/{season}/{source_run}"
    private_tag = f"{PRIVATE_MANAGER_PREFIX}/{season}/{source_run}"
    presentation_tag = f"{PRESENTATION_PREFIX}/{season}/{source_run}"
    existing = _find_release(private_releases, presentation_tag)
    if existing is not None:
        if not bool(existing.get("immutable", False)):
            raise RuntimeError("existing owner brief release is not immutable")
        if frozenset(release_asset_map(existing)) != PRESENTATION_ASSETS:
            raise RuntimeError("existing owner brief release asset contract mismatch")
        return presentation_tag
    public_release = _find_release(public_releases, public_tag)
    private_release = _find_release(private_releases, private_tag)
    if public_release is None or private_release is None:
        raise RuntimeError("matching public/private source release is unavailable")
    if not bool(public_release.get("immutable", False)) or not bool(private_release.get("immutable", False)):
        raise RuntimeError("owner brief sources must be immutable")
    if frozenset(release_asset_map(public_release)) != PUBLIC_RELEASE_ASSETS_V1:
        raise RuntimeError("public source asset contract mismatch")
    if frozenset(release_asset_map(private_release)) != PRIVATE_RELEASE_ASSETS_V1:
        raise RuntimeError("private source asset contract mismatch")

    with tempfile.TemporaryDirectory(prefix="apex-owner-brief-") as tmp:
        root = Path(tmp)
        public_files = {
            name: download_release_asset(public_store, public_release, name, root / "public" / name)
            for name in sorted(PUBLIC_RELEASE_ASSETS_V1)
        }
        verify_public_attestation(public_files)
        private_attempt_path = download_release_asset(
            private_store, private_release, "private_manager_attempt.json", root / "private" / "private_manager_attempt.json"
        )
        private_attestation_path = download_release_asset(
            private_store, private_release, "private_attestation.json", root / "private" / "private_attestation.json"
        )
        private_attestation = json.loads(private_attestation_path.read_text(encoding="utf-8"))
        private_sha = sha256_path(private_attempt_path)
        public_attempt = json.loads(public_files["public_attempt.json"].read_text(encoding="utf-8"))
        if private_attestation.get("scope") != "PRIVATE_MANAGER":
            raise RuntimeError("private manager attestation scope mismatch")
        if private_attestation.get("assets") != {"private_manager_attempt.json": private_sha}:
            raise RuntimeError("private manager attestation hash mismatch")
        if str(private_attestation.get("public_attempt_id") or "") != str(public_attempt.get("public_attempt_id") or ""):
            raise RuntimeError("private manager attestation identity mismatch")
        private_attempt = json.loads(private_attempt_path.read_text(encoding="utf-8"))
        governance = json.loads(public_files["governance.json"].read_text(encoding="utf-8"))
        brief = build_owner_brief(
            private_attempt,
            public_attempt,
            governance,
            source_private_sha256=private_sha,
            control_plane_sha=control_plane_sha,
        )
        brief_json = root / "owner_brief.json"
        brief_md = root / "owner_brief.md"
        brief_json.write_bytes(canonical_bytes(brief) + b"\n")
        brief_md.write_text(render_markdown(brief), encoding="utf-8")
        attestation = {
            "schema_version": 1,
            "contract": "APEX_V2_OWNER_BRIEF_ATTESTATION_V1",
            "source_public_attempt_id": brief["source"]["public_attempt_id"],
            "source_private_manager_sha256": private_sha,
            "assets": {
                "owner_brief.json": sha256_path(brief_json),
                "owner_brief.md": sha256_path(brief_md),
            },
        }
        attestation_path = root / "owner_brief_attestation.json"
        attestation_path.write_bytes(canonical_bytes(attestation) + b"\n")
        ref = private_store.create_once(
            presentation_tag,
            {
                "owner_brief.json": brief_json,
                "owner_brief.md": brief_md,
                "owner_brief_attestation.json": attestation_path,
            },
            target_commitish=None,
            name=f"Apex V2 owner brief {season} GW{brief['source']['target_gameweek']} {source_run}",
            body="Owner-private, read-only rendering of an immutable Apex V2 decision. No serving authority.",
        )
        if not ref.immutable:
            raise RuntimeError("owner brief release is not immutable")
    return presentation_tag


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", default="2026-2027")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--control-plane-sha", required=True)
    args = parser.parse_args()
    tag = run_publish(season=args.season, run_id=args.run_id, control_plane_sha=args.control_plane_sha)
    print(json.dumps({"published_or_verified": tag, "production_influence": "NONE"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
