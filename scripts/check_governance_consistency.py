#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


AUTHORITY = "docs/APEX_OPERATING_MANUAL.md"
REQUIRED_REDIRECTS = (
    "docs/CHATGPT_USAGE.md",
    "docs/CHATGPT_APEX_QUERY_POLICY.md",
    "docs/CURRENT_STATE.md",
    "docs/APEX_ROADMAP.md",
    "docs/KNOWN_ISSUES.md",
)
FINAL_SELECTORS = (
    "adaptive_gw1_launch_with_transfer_option_value",
    "receding_horizon_current_team_maximum_ev",
)
FINAL_PROMOTION_ENTRYPOINTS = (
    "scripts/apply_joint_path_promotion.py",
    "scripts/apply_joint_path_promotion_rebased.py",
)
ACTIVE_WORKFLOWS = {
    "airsenal.yml",
    "apex-v2-auth-keepalive.yml",
    "apex-v2-daily-evaluation.yml",
    "apex-v2-daily-production.yml",
    "apex-v2-deadline-watch.yml",
    "apex-v2-decision-quality.yml",
    "apex-v2-direct-auth-diagnostic.yml",
    "apex-v2-ops-contract.yml",
    "apex-v2-owner-brief.yml",
    "apex-v2-prospective-tournament.yml",
    "apex-v2-shadow-health.yml",
    "apex.yml",
    "gw1-final-2026.yml",
    "joint-path-promotion-audit.yml",
    "pinnacle.yml",
    "production-readiness.yml",
    "projection-policy-audit.yml",
    "projection-shadow-audit.yml",
    "refresh-core-pin.yml",
    "team-strength-validation.yml",
    "understat-player-production-ab.yml",
}
ARCHIVED_WORKFLOWS = {
    "bootstrap-publish.yml",
    "publish-apex.yml",
    "fixture-blend-decision-audit.yml",
    "joint-initial-path-audit.yml",
    "solver-parity.yml",
    "understat-player-predictive-audit.yml",
}
CONCURRENT_PR_AUDITS = {
    "apex.yml": "github.event.pull_request.number || github.ref",
    "joint-path-promotion-audit.yml": "github.event.pull_request.number || github.ref",
    "projection-policy-audit.yml": "github.event.pull_request.number || github.ref",
    "projection-shadow-audit.yml": "github.event.pull_request.number || github.ref",
    "team-strength-validation.yml": "github.event.pull_request.number || github.ref",
    "understat-player-production-ab.yml": "github.event.pull_request.number || github.ref",
}
REQUIRED_SOURCE_INVALIDATORS = {
    "airsenal.yml": "--source airsenal",
    "refresh-core-pin.yml": "--source fpl_core_insights",
}


def _text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def main() -> None:
    failures: list[str] = []
    authority = Path(AUTHORITY)
    if not authority.exists():
        failures.append(f"missing authority document: {AUTHORITY}")
    for name in REQUIRED_REDIRECTS:
        text = _text(name)
        if "APEX_OPERATING_MANUAL.md" not in text:
            failures.append(f"{name} does not redirect to {AUTHORITY}")

    active_dir = Path(".github/workflows")
    active = {path.name for path in active_dir.glob("*.yml")}
    if active != ACTIVE_WORKFLOWS:
        failures.append(
            "active workflow surface drifted: "
            f"expected={sorted(ACTIVE_WORKFLOWS)} actual={sorted(active)}"
        )
    archive_dir = Path("archive/workflows")
    archived = {path.name for path in archive_dir.glob("*.yml")}
    missing_archived = sorted(ARCHIVED_WORKFLOWS - archived)
    if missing_archived:
        failures.append(
            f"superseded workflows are missing from archive: {missing_archived}"
        )
    if not (archive_dir / "README.md").exists():
        failures.append("workflow archive manifest is missing")
    for name in ARCHIVED_WORKFLOWS:
        if (active_dir / name).exists():
            failures.append(f"superseded workflow remains executable: {name}")

    for name, group_expr in CONCURRENT_PR_AUDITS.items():
        text = _text(active_dir / name)
        if "cancel-in-progress: true" not in text or group_expr not in text:
            failures.append(
                f"expensive PR workflow does not cancel superseded runs: {name}"
            )

    if not Path("scripts/invalidate_published_decision.py").exists():
        failures.append("required-source canonical invalidation CLI is missing")
    for name, source_arg in REQUIRED_SOURCE_INVALIDATORS.items():
        text = _text(active_dir / name)
        if (
            "scripts/invalidate_published_decision.py" not in text
            or source_arg not in text
        ):
            failures.append(
                f"required-source refresh can leave a stale actionable decision: {name}"
            )
        if (
            "apex_answer_context.json" not in text
            or "apex_recommendation_latest.json" not in text
        ):
            failures.append(
                f"required-source refresh does not atomically stage invalidated canonical files: {name}"
            )

    workflow = _text(active_dir / "pinnacle.yml")
    if "scripts/run_apex.py" not in workflow:
        failures.append("production workflow does not use the single Apex runner")
    if "apex_answer_context.json" not in workflow:
        failures.append("production workflow does not publish apex_answer_context.json")
    if "scripts/build_decision_bundle.py" not in workflow:
        failures.append("production workflow does not seal a decision bundle")
    if "data/generated/decision_bundle" not in workflow:
        failures.append("production workflow does not retain the decision bundle artifact")

    for script_name in ("scripts/run_pinnacle.py", "scripts/run_elite.py"):
        script = _text(script_name)
        if "DecisionBundle.load" not in script:
            failures.append(f"{script_name} does not consume the sealed decision bundle")
        if "run_pipeline" in script or "OfficialFPLClient" in script:
            failures.append(
                f"{script_name} contains an independent live retrieval path"
            )

    staging = _text("scripts/build_canonical_recommendation.py")
    if (
        "strategy_base_ready" not in staging
        or '"ready_to_act": False' not in staging
    ):
        failures.append("canonical base builder is not explicitly staging-only")
    if '"recommendation": None' not in staging:
        failures.append("canonical base builder can expose an intermediate recommendation")
    if (
        "exact_horizon_staging" not in staging
        or '"authority": False' not in staging
    ):
        failures.append(
            "static exact-horizon result is not explicitly diagnostic-only"
        )

    finaliser = _text("scripts/apply_joint_path_promotion.py")
    for selector in FINAL_SELECTORS:
        if selector not in finaliser:
            failures.append(f"final strategy assembler lacks selector: {selector}")
    if "build_selected_player_evidence" not in finaliser:
        failures.append(
            "final strategy assembler does not rebuild evidence for the actual final 15"
        )
    if "final_selected_player_evidence" not in finaliser:
        failures.append(
            "final strategy assembler does not publish final evidence identity"
        )
    if "all_player_truth" not in finaliser:
        failures.append("final strategy assembler does not require all-player truth")

    runner = _text("scripts/run_apex.py")
    truth_pos = runner.find("scripts/audit_player_truth.py")
    final_positions = [runner.find(name) for name in FINAL_PROMOTION_ENTRYPOINTS]
    final_positions = [pos for pos in final_positions if pos >= 0]
    final_pos = min(final_positions) if final_positions else -1
    if truth_pos < 0 or final_pos < 0 or truth_pos > final_pos:
        failures.append(
            "single Apex runner does not gate final selection behind all-player truth"
        )

    answer = _text("src/apex_fpl/services/answer_context.py")
    for selector in FINAL_SELECTORS:
        if selector not in answer:
            failures.append(f"answer contract does not recognise final selector: {selector}")
    if "final_selected_player_evidence" not in answer:
        failures.append(
            "answer contract does not use the actual final selected-player evidence"
        )
    if '"selection_regret": None' not in answer:
        failures.append(
            "answer contract can misattribute static exact-horizon regret to final picks"
        )

    canonical_policy = _text("docs/APEX_CANONICAL_DECISION_POLICY.md")
    architecture = _text("docs/APEX_ARCHITECTURE.md")
    operating = _text(AUTHORITY)
    for selector in FINAL_SELECTORS:
        if selector not in canonical_policy:
            failures.append(f"canonical decision policy is stale for selector: {selector}")
    if "GW1-first" not in architecture or "receding-horizon" not in architecture:
        failures.append(
            "architecture document does not describe the final adaptive strategy"
        )
    if "adverse-evidence-only" not in operating:
        failures.append("operating manual does not preserve the EV-first evidence policy")
    if "architecture freeze" not in operating.casefold():
        failures.append(
            "operating manual does not define the post-PR64 architecture freeze"
        )

    gw1 = _text(active_dir / "gw1-final-2026.yml")
    if "scripts/run_apex.py" not in gw1:
        failures.append("GW1 final workflow bypasses the single canonical runner")

    shadow = _text(active_dir / "apex-v2-shadow-health.yml")
    for needle in (
        "contents: read",
        "99cc7b51b0cff45462b567084cb1844cfe0a456f",
        "dastan-pin-health",
        "pitchside-health",
        "openfpl-readiness",
        "\n  push:\n",
        "      - main",
        '      - ".github/workflows/apex-v2-shadow-health.yml"',
        '      - "scripts/apex_v2_shadow_provider_ops.py"',
    ):
        if needle not in shadow:
            failures.append(
                f"shadow-provider health workflow missing safety contract: {needle}"
            )
    for forbidden in (
        "FPL_SESSION_COOKIE",
        "FPL_X_API_AUTHORIZATION",
        "FPL_REFRESH_TOKEN",
        "APEX_PRIVATE_GITHUB_TOKEN",
        "apex-v2 solve",
        "apex-v2 publish",
        "contents: write",
    ):
        if forbidden in shadow:
            failures.append(
                f"shadow-provider health workflow crossed serving boundary: {forbidden}"
            )

    tournament = _text(active_dir / "apex-v2-prospective-tournament.yml")
    for needle in (
        'workflows: ["Apex V2 Daily Production"]',
        'cron: "23 * * * *"',
        "99cc7b51b0cff45462b567084cb1844cfe0a456f",
        "apex_v2_tournament_common.py",
        "apex_v2_tournament_contract.py",
        "apex_v2_tournament_ops.py",
        "apex_v2_tournament_scoring.py",
        "seal-run",
        "retain-gw2",
        "canonicalize",
        "evaluate",
        "status",
        "\n  push:\n",
        "      - main",
        "EARLIEST_FUTURE_DEADLINE_THEN_LATEST_VALID_FROZEN_AT",
        "NO_ELIGIBLE_SOURCE",
        'echo "has_source=false"',
        "steps.source.outputs.has_source == 'true'",
        'release.get("immutable") is not True',
        'get("personalized_actionable") is not True',
        "frozen_at >= deadline or now >= deadline",
        '!= "airsenal" for h in range(1, 9)',
    ):
        if needle not in tournament:
            failures.append(
                f"prospective tournament workflow missing safety contract: {needle}"
            )
    for forbidden in (
        "FPL_SESSION_COOKIE",
        "FPL_X_API_AUTHORIZATION",
        "FPL_REFRESH_TOKEN",
        "apex-v2 intent",
        "apex-v2 official-hash",
        "apex-v2 acquire",
        "apex-v2 solve",
        "apex-v2 publish",
        "scripts/acquire_dastan_shadow.py",
        "run_airsenal_worker.py",
    ):
        if forbidden in tournament:
            failures.append(
                f"prospective tournament workflow crossed serving boundary: {forbidden}"
            )

    tournament_common = _text("scripts/apex_v2_tournament_common.py")
    for needle in (
        "DIAGNOSTIC_REHEARSAL_NON_CANONICAL",
        "PROSPECTIVE_READY_CANDIDATE",
        "CANONICAL_PROSPECTIVE_OBSERVATION",
        "TRAINING_READY_NO_MODEL",
        "OFFICIAL_UNAVAILABLE_NO_FORECAST_EXPECTED",
    ):
        if needle not in tournament_common:
            failures.append(
                f"prospective tournament common contract missing: {needle}"
            )

    tournament_contract = _text("scripts/apex_v2_tournament_contract.py")
    for needle in (
        "LAST_VALID_COMMON_PREDEADLINE_SEAL",
        '"production_influence": "NONE"',
        '"serve_authorized": False',
        '"eligible_common_predeadline_candidate": ready',
        '"history_commit": row.get("observed_history_commit")',
        "COMMON_FORECAST_INTERSECTION",
    ):
        if needle not in tournament_contract:
            failures.append(
                f"prospective tournament governance contract missing: {needle}"
            )

    tournament_scoring = _text("scripts/apex_v2_tournament_scoring.py")
    for needle in (
        "score_predictions",
        "COMMON_FORECAST_INTERSECTION",
        "CATASTROPHIC_XP_RESIDUAL",
        "entered provider surface missing at evaluation",
        "NOT_SCOREABLE_NO_REALIZED_START_LABEL",
    ):
        if needle not in tournament_scoring:
            failures.append(
                f"prospective tournament scoring contract missing: {needle}"
            )

    tournament_ops = _text("scripts/apex_v2_tournament_ops.py")
    for needle in (
        "existing candidate run identity mismatch",
        "immutable private tournament supplement already exists with different bytes",
        "published tournament selection exists without immutability",
        "gw3_prospective_tournament_ready",
        "evaluator changed the sealed entrant set",
    ):
        if needle not in tournament_ops:
            failures.append(
                f"prospective tournament orchestration contract missing: {needle}"
            )

    tournament_doc = _text("docs/APEX_V2_PROSPECTIVE_TOURNAMENT.md")
    for needle in (
        "GW2",
        "DIAGNOSTIC_REHEARSAL_NON_CANONICAL",
        "GW3",
        "LAST_VALID_COMMON_PREDEADLINE_SEAL",
        "Universal H1",
        "Strategic H2-H8",
        "TRAINING_READY_NO_MODEL",
        "production_influence",
        "NONE",
    ):
        if needle not in tournament_doc:
            failures.append(
                f"prospective tournament documentation missing: {needle}"
            )

    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
