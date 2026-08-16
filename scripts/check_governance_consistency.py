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
ARCHIVED_PUBLISHERS = (
    ".github/workflows/publish-apex.yml",
    ".github/workflows/bootstrap-publish.yml",
)


def _text(path: str) -> str:
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

    workflow = _text(".github/workflows/pinnacle.yml")
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
    final_pos = runner.find("scripts/apply_joint_path_promotion.py")
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

    for archived in ARCHIVED_PUBLISHERS:
        text = _text(archived)
        if "git push" in text:
            failures.append(f"archived workflow can still push production state: {archived}")

    gw1 = _text(".github/workflows/gw1-final-2026.yml")
    if "scripts/run_apex.py" not in gw1:
        failures.append("GW1 final workflow bypasses the single canonical runner")

    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
