#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re


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
    "v2-shadow-production.yml",
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
RUNTIME_ARTIFACT_WORKFLOWS = {
    "airsenal.yml",
    "pinnacle.yml",
    "refresh-core-pin.yml",
}
ACTION_REF = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.MULTILINE)
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


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
        failures.append(f"superseded workflows are missing from archive: {missing_archived}")
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

    # Runtime/source separation and immutable CI dependencies are constitutional.
    for name in ACTIVE_WORKFLOWS:
        text = _text(active_dir / name)
        if "contents: write" in text:
            failures.append(f"active workflow has source write permission: {name}")
        if "git push origin HEAD:main" in text:
            failures.append(f"active workflow directly pushes runtime/source state to main: {name}")
        for reference in ACTION_REF.findall(text):
            if reference.startswith("./") or reference.startswith("docker://"):
                continue
            if "@" not in reference:
                failures.append(f"active workflow action lacks immutable ref: {name}: {reference}")
                continue
            action, ref = reference.rsplit("@", 1)
            if not FULL_SHA.fullmatch(ref):
                failures.append(f"active workflow action is mutable: {name}: {action}@{ref}")

    for name in RUNTIME_ARTIFACT_WORKFLOWS:
        text = _text(active_dir / name)
        if "contents: read" not in text:
            failures.append(f"runtime artifact workflow is not read-only: {name}")

    airsenal = _text(active_dir / "airsenal.yml")
    if "actions/upload-artifact@" not in airsenal or "data/generated/airsenal.csv" not in airsenal:
        failures.append("AIrsenal validation workflow does not retain its runtime artifact")
    if "invalidate_published_decision.py" in airsenal:
        failures.append("AIrsenal validation still mutates a tracked published decision")

    core_pin = _text(active_dir / "refresh-core-pin.yml")
    if "actions/upload-artifact@" not in core_pin or "upstreams.lock.json" not in core_pin:
        failures.append("FPL Core pin audit does not retain the validated proposal artifact")
    if "reviewed dependency source change required" not in core_pin:
        failures.append("FPL Core pin audit does not enforce reviewed source promotion")
    if "invalidate_published_decision.py" in core_pin:
        failures.append("FPL Core pin audit still mutates a tracked published decision")

    workflow = _text(active_dir / "pinnacle.yml")
    if "scripts/run_apex.py" not in workflow:
        failures.append("production workflow does not use the single Apex runner")
    if "apex_answer_context.json" not in workflow:
        failures.append("production workflow does not retain apex_answer_context.json in its runtime packet")
    if "scripts/build_decision_bundle.py" not in workflow:
        failures.append("production workflow does not seal a decision bundle")
    if "data/generated/decision_bundle" not in workflow:
        failures.append("production workflow does not retain the decision bundle artifact")
    if "scripts/stage_runtime_release.py" not in workflow:
        failures.append("production workflow does not stage an immutable runtime release")

    for script_name in ("scripts/run_pinnacle.py", "scripts/run_elite.py"):
        script = _text(script_name)
        if "DecisionBundle.load" not in script:
            failures.append(f"{script_name} does not consume the sealed decision bundle")
        if "run_pipeline" in script or "OfficialFPLClient" in script:
            failures.append(f"{script_name} contains an independent live retrieval path")

    staging = _text("scripts/build_canonical_recommendation.py")
    if "strategy_base_ready" not in staging or '"ready_to_act": False' not in staging:
        failures.append("canonical base builder is not explicitly staging-only")
    if '"recommendation": None' not in staging:
        failures.append("canonical base builder can expose an intermediate recommendation")
    if "exact_horizon_staging" not in staging or '"authority": False' not in staging:
        failures.append("static exact-horizon result is not explicitly diagnostic-only")

    finaliser = _text("scripts/apply_joint_path_promotion.py")
    for selector in FINAL_SELECTORS:
        if selector not in finaliser:
            failures.append(f"final strategy assembler lacks selector: {selector}")
    if "build_selected_player_evidence" not in finaliser:
        failures.append("final strategy assembler does not rebuild evidence for the actual final 15")
    if "final_selected_player_evidence" not in finaliser:
        failures.append("final strategy assembler does not publish final evidence identity")
    if "all_player_truth" not in finaliser:
        failures.append("final strategy assembler does not require all-player truth")

    runner = _text("scripts/run_apex.py")
    truth_pos = runner.find("scripts/audit_player_truth.py")
    final_positions = [runner.find(name) for name in FINAL_PROMOTION_ENTRYPOINTS]
    final_positions = [pos for pos in final_positions if pos >= 0]
    final_pos = min(final_positions) if final_positions else -1
    if truth_pos < 0 or final_pos < 0 or truth_pos > final_pos:
        failures.append("single Apex runner does not gate final selection behind all-player truth")

    answer = _text("src/apex_fpl/services/answer_context.py")
    for selector in FINAL_SELECTORS:
        if selector not in answer:
            failures.append(f"answer contract does not recognise final selector: {selector}")
    if "final_selected_player_evidence" not in answer:
        failures.append("answer contract does not use the actual final selected-player evidence")
    if '"selection_regret": None' not in answer:
        failures.append("answer contract can misattribute static exact-horizon regret to final picks")

    canonical_policy = _text("docs/APEX_CANONICAL_DECISION_POLICY.md")
    architecture = _text("docs/APEX_ARCHITECTURE.md")
    operating = _text(AUTHORITY)
    for selector in FINAL_SELECTORS:
        if selector not in canonical_policy:
            failures.append(f"canonical decision policy is stale for selector: {selector}")
    if "GW1-first" not in architecture or "receding-horizon" not in architecture:
        failures.append("architecture document does not describe the final adaptive strategy")
    if "adverse-evidence-only" not in operating:
        failures.append("operating manual does not preserve the EV-first evidence policy")
    if "architecture freeze" not in operating.casefold():
        failures.append("operating manual does not define the post-PR64 architecture freeze")

    gw1 = _text(active_dir / "gw1-final-2026.yml")
    if "scripts/run_apex.py" not in gw1:
        failures.append("GW1 final workflow bypasses the single canonical runner")

    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
