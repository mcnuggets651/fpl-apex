from __future__ import annotations

import json
import os
from pathlib import Path

from apex.decision.optimiser import optimise_initial_squad
from apex.decision.transfers import optimise_transfer_horizon
from apex.domain.models import (
    DecisionBundle,
    EvidenceEffect,
    EvidenceRecord,
    ProductionProjectionSurface,
    ProviderHealth,
    ProviderRole,
    ProviderStatus,
    Qualification,
    RunManifest,
    dataclass_to_dict,
)
from apex.forecast.contract import projection_surface_hash
from apex.forecast.registry import (
    max_contiguous_qualified_horizon,
    serving_policy,
)
from apex.governance.certification import certify
from apex.governance.evidence import hard_exclusions

from .serde import official_from_dict, projection_from_dict, team_from_dict
from .snapshot import open_frozen_snapshot


def _status_from_row(row, surface):
    return ProviderStatus(
        row["provider_id"],
        ProviderRole(row["role"]),
        int(row["priority"]),
        ProviderHealth(row["health"]),
        {
            int(key): Qualification(value)
            for key, value in row["qualification_by_horizon"].items()
        },
        surface,
        tuple(row.get("reasons", [])),
        bool(row.get("serve_authorized", False)),
        Qualification(
            row.get("predictive_status", "INSUFFICIENT_HISTORY")
        ),
    )


def _canonical(policy, max_horizon):
    rows = []
    provider_ids = []
    versions = []
    first_surface = None
    for horizon in range(1, max_horizon + 1):
        provider = policy[horizon]
        first_surface = first_surface or provider.surface
        provider_ids.append(provider.provider_id)
        versions.append(
            f"{provider.provider_id}:{provider.surface.provider_version}"
        )
        rows.extend(
            row
            for row in provider.surface.rows
            if row.horizon == horizon
        )
    return ProductionProjectionSurface(
        1,
        "|".join(provider_ids),
        "|".join(versions),
        max(
            provider.surface.generated_at
            for provider in policy.values()
        ),
        first_surface.season,
        first_surface.source_snapshot,
        first_surface.scoring_rules_version,
        tuple(range(1, max_horizon + 1)),
        tuple(rows),
    )


def _evidence_acquisition_state(snapshot, run, official):
    required = bool(run.get("evidence_required", False))
    try:
        payload = snapshot.read_json("evidence_acquisition.json")
    except (KeyError, FileNotFoundError):
        payload = {}
    if not required:
        return True, payload, ()
    complete = bool(
        isinstance(payload, dict)
        and payload.get("completed") is True
        and str(payload.get("observed_official_hash") or "")
        == str(official.source_hash)
        and int(payload.get("target_gameweek", -1))
        == int(run["target_gameweek"])
        and not (payload.get("required_source_failures") or [])
    )
    warnings = []
    if not complete:
        warnings.append(
            "required external evidence acquisition is missing, incomplete, "
            "or not bound to this Official FPL snapshot"
        )
    return complete, payload, tuple(warnings)


def solve_snapshot(snapshot_path: Path, output: Path) -> DecisionBundle:
    if os.getenv("APEX_ALLOW_NETWORK_DURING_SOLVE", "0") == "1":
        raise RuntimeError(
            "network override is forbidden in production solve"
        )

    snapshot = open_frozen_snapshot(snapshot_path)
    official = official_from_dict(snapshot.read_json("official.json"))
    team_raw = snapshot.read_json("team_state.json")
    team = team_from_dict(team_raw) if team_raw else None
    run = snapshot.read_json("run.json")
    matrix = snapshot.read_json("qualification_matrix.json")

    statuses = []
    for row in matrix:
        try:
            surface = projection_from_dict(
                snapshot.read_json(f"providers/{row['provider_id']}.json")
            )
        except (KeyError, FileNotFoundError):
            surface = None
        statuses.append(_status_from_row(row, surface))

    universe = official.decision_universe(
        set(team.squad_ids) if team else frozenset()
    )
    policy = serving_policy(
        statuses,
        max_horizon=int(run["max_horizon"]),
        decision_universe=universe,
    )
    max_horizon = max_contiguous_qualified_horizon(policy)
    serving_h1 = policy.get(1)
    decision = None
    warnings = []
    decision_optimisation = {
        "kind": "NONE",
        "status": "NOT_RUN",
        "solver": {},
        "weeks": [],
    }

    evidence_rows = snapshot.read_json("evidence.json")
    records = tuple(
        EvidenceRecord(
            str(row["evidence_id"]),
            int(row["element_id"]),
            row["source_name"],
            row["source_url"],
            row["source_tier"],
            row["published_at"],
            row["retrieved_at"],
            row["expires_at"],
            row["evidence_type"],
            int(row["gameweek"]),
            EvidenceEffect(row["effect"]),
            row["content_hash"],
            row.get("excerpt", ""),
        )
        for row in evidence_rows
    )
    excluded = hard_exclusions(records, int(run["target_gameweek"]))
    (
        evidence_acquisition_complete,
        evidence_acquisition,
        evidence_acquisition_warnings,
    ) = _evidence_acquisition_state(snapshot, run, official)
    warnings.extend(evidence_acquisition_warnings)

    for source in evidence_acquisition.get("sources", []) if isinstance(evidence_acquisition, dict) else []:
        if source.get("required") is not True and source.get("status") == "FAILED":
            warnings.append(
                "optional evidence source failed: "
                f"{source.get('name', 'unknown')} ({source.get('error', 'unknown error')})"
            )

    if max_horizon >= 1:
        canonical = _canonical(policy, max_horizon)
        if team is None:
            result = optimise_initial_squad(
                official,
                canonical,
                horizon=1,
                excluded_ids=excluded,
            )
            decision = result.decision
            decision_optimisation = {
                "kind": "INITIAL_SQUAD",
                "status": result.status,
                "solver": result.raw_solver,
                "weeks": [],
            }
            if result.status == "INFEASIBLE":
                warnings.append("initial optimiser infeasible")
        else:
            transfer_result = optimise_transfer_horizon(
                official,
                canonical,
                team,
                max_horizon=max_horizon,
                excluded_h1=excluded,
            )
            decision = transfer_result.decision
            decision_optimisation = {
                "kind": "TRANSFER_HORIZON",
                "status": transfer_result.status,
                "primary_objective": transfer_result.primary_objective,
                "solver": transfer_result.solver,
                "week_count": len(transfer_result.weeks),
                "weeks": [
                    dataclass_to_dict(week)
                    for week in transfer_result.weeks
                ],
            }
            reason = transfer_result.solver.get("reason")
            message = transfer_result.solver.get("message")
            if transfer_result.status == "INFEASIBLE":
                detail = reason or message or "solver returned no feasible solution"
                warnings.append(f"transfer optimiser infeasible: {detail}")
            elif reason:
                warnings.append(reason)

        horizon_rows = {
            row.element_id: row
            for row in canonical.rows_for_horizon(1)
        }
        if decision and not all(
            horizon_rows.get(player_id)
            and horizon_rows[player_id].p_appearance is not None
            for player_id in decision.squad_ids
        ):
            warnings.append(
                "appearance probabilities incomplete: contingent autosub/vice "
                "fallback EV is not included in primary objective"
            )
        canonical_hash = projection_surface_hash(canonical)
    else:
        canonical_hash = ""
        decision_optimisation = {
            "kind": "NONE",
            "status": "NOT_RUN_NO_SERVING_PROVIDER",
            "solver": {},
            "weeks": [],
        }
        warnings.append("no authorized complete H1 serving provider")

    for status in statuses:
        if status.role == ProviderRole.SHADOW and status.reasons:
            warnings.append(
                f"shadow {status.provider_id}: {'; '.join(status.reasons)}"
            )

    evidence_errors = snapshot.read_json(
        "evidence_validation.json"
    ).get("errors", [])
    certification = certify(
        official=official,
        serving=serving_h1,
        decision=decision,
        team_state=team,
        hard_evidence_conflict=bool(evidence_errors),
        evidence_acquisition_complete=evidence_acquisition_complete,
        degraded_warnings=tuple(warnings),
        valid_until=run["deadline"],
    )
    manifest = RunManifest(
        1,
        run["run_id"],
        os.getenv("GITHUB_RUN_ID"),
        run["season"],
        int(run["target_gameweek"]),
        run["code_sha"],
        run["config_sha"],
        run["acquired_at"],
        snapshot.snapshot_id,
        {
            horizon: provider.provider_id
            for horizon, provider in policy.items()
        },
        run["run_started_at"],
        snapshot.manifest.get("metadata", {}).get("frozen_at", ""),
    )
    bundle = DecisionBundle(
        1,
        manifest,
        official.source_hash,
        canonical_hash,
        decision,
        certification,
        {
            "statuses": matrix,
            "max_contiguous_horizon": max_horizon,
            "serving_provider_by_horizon": {
                str(horizon): provider.provider_id
                for horizon, provider in policy.items()
            },
            "decision_optimisation": decision_optimisation,
        },
        {
            "hard_evidence_count": len(records),
            "hard_exclusion_count": len(excluded),
            "validation_errors": evidence_errors,
            "acquisition": evidence_acquisition,
        },
    )

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            dataclass_to_dict(bundle),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )
    os.replace(temporary, output)
    return bundle
