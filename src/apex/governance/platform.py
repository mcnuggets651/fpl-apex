from __future__ import annotations

from typing import Any


def _ruleset_targets_branch(
    ruleset: dict[str, Any],
    accepted_ref_targets: set[str],
) -> bool:
    conditions = ruleset.get("conditions") or {}
    ref_name = conditions.get("ref_name") or {}
    included = {str(value) for value in ref_name.get("include", ())}
    excluded = {str(value) for value in ref_name.get("exclude", ())}
    return bool(included & accepted_ref_targets) and not bool(
        excluded & accepted_ref_targets
    )


def _required_status_rule(ruleset: dict[str, Any]) -> dict[str, Any] | None:
    for rule in ruleset.get("rules", ()):
        if rule.get("type") == "required_status_checks":
            return rule
    return None


def validate_platform_controls(
    branch: dict[str, Any],
    rulesets: list[dict[str, Any]],
    immutable_status_code: int,
    immutable_payload: dict[str, Any] | None,
    policy: dict[str, Any],
) -> tuple[str, ...]:
    """Validate live GitHub controls required before V2 cutover.

    Acquisition is intentionally outside this function. Production workflows freeze
    GitHub API responses first, then this deterministic validator evaluates them.
    """
    errors: list[str] = []
    if int(policy.get("schema_version", -1)) != 1:
        errors.append("cutover platform policy schema_version must be 1")
    if str(policy.get("policy_id", "")) != "apex-v2-cutover-platform-v1":
        errors.append("unexpected cutover platform policy_id")

    default_branch = str(policy.get("default_branch", ""))
    if str(branch.get("name", "")) != default_branch:
        errors.append(
            f"branch evidence is for {branch.get('name')!r}, expected {default_branch!r}"
        )

    branch_policy = policy.get("branch_governance") or {}
    if branch_policy.get("require_protected_branch") is True:
        if branch.get("protected") is not True:
            errors.append(f"{default_branch} is not protected")

    accepted_targets = {
        str(value) for value in branch_policy.get("accepted_ref_targets", ())
    }
    candidates = [
        ruleset
        for ruleset in rulesets
        if str(ruleset.get("target", "")) == "branch"
        and str(ruleset.get("enforcement", "")) == "active"
        and _ruleset_targets_branch(ruleset, accepted_targets)
    ]
    if (
        branch_policy.get("require_active_repository_ruleset") is True
        and not candidates
    ):
        errors.append("no active repository ruleset protects the default branch")

    required_rule_types = {
        str(value) for value in branch_policy.get("required_rule_types", ())
    }
    required_checks = {
        str(value) for value in branch_policy.get("required_status_checks", ())
    }
    require_strict = (
        branch_policy.get("strict_required_status_checks_policy") is True
    )
    forbid_bypass = branch_policy.get("allow_bypass_actors") is False

    satisfying_ruleset = False
    candidate_diagnostics: list[str] = []
    for ruleset in candidates:
        name = str(ruleset.get("name") or ruleset.get("id") or "unnamed")
        rule_types = {
            str(rule.get("type"))
            for rule in ruleset.get("rules", ())
            if rule.get("type") is not None
        }
        missing_types = sorted(required_rule_types - rule_types)
        if missing_types:
            candidate_diagnostics.append(
                f"ruleset {name!r} missing rules: {', '.join(missing_types)}"
            )
            continue

        status_rule = _required_status_rule(ruleset)
        parameters = (status_rule or {}).get("parameters") or {}
        contexts = {
            str(row.get("context"))
            for row in parameters.get("required_status_checks", ())
            if row.get("context") is not None
        }
        missing_checks = sorted(required_checks - contexts)
        if missing_checks:
            candidate_diagnostics.append(
                f"ruleset {name!r} missing required checks: {', '.join(missing_checks)}"
            )
            continue
        if (
            require_strict
            and parameters.get("strict_required_status_checks_policy") is not True
        ):
            candidate_diagnostics.append(
                f"ruleset {name!r} does not require strict/up-to-date status checks"
            )
            continue
        if forbid_bypass and ruleset.get("bypass_actors"):
            candidate_diagnostics.append(
                f"ruleset {name!r} contains bypass actors"
            )
            continue
        satisfying_ruleset = True
        break

    if candidates and not satisfying_ruleset:
        errors.extend(
            candidate_diagnostics or ["default-branch ruleset is incomplete"]
        )

    release_policy = policy.get("release_governance") or {}
    if release_policy.get("immutable_releases_required") is True:
        enabled_code = int(release_policy.get("enabled_status_code", 200))
        disabled_code = int(release_policy.get("disabled_status_code", 404))
        if immutable_status_code == disabled_code:
            errors.append("GitHub immutable releases are disabled")
        elif immutable_status_code != enabled_code:
            errors.append(
                "GitHub immutable-release setting could not be verified: "
                f"HTTP {immutable_status_code}"
            )
        elif (
            not isinstance(immutable_payload, dict)
            or immutable_payload.get("enabled") is not True
        ):
            errors.append(
                "GitHub immutable-release endpoint did not return enabled=true"
            )

    return tuple(dict.fromkeys(errors))
