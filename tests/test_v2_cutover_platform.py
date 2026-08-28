from __future__ import annotations

import copy
from pathlib import Path

import yaml

from apex.governance.platform import validate_platform_controls

ROOT = Path(__file__).resolve().parents[1]


def policy():
    return yaml.safe_load(
        (ROOT / "config/apex_v2_cutover_platform.yaml").read_text(encoding="utf-8")
    )


def protected_branch():
    return {
        "name": "main",
        "protected": True,
        "protection": {
            "enabled": True,
            "required_status_checks": {"enforcement_level": "required"},
        },
    }


def compliant_ruleset():
    return {
        "id": 123,
        "name": "Apex V2 main protection",
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {
            "ref_name": {
                "include": ["refs/heads/main"],
                "exclude": [],
            }
        },
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {
                "type": "pull_request",
                "parameters": {
                    "allowed_merge_methods": ["merge", "squash", "rebase"],
                },
            },
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": True,
                    "do_not_enforce_on_create": False,
                    "required_status_checks": [
                        {"context": "test"},
                        {"context": "contract"},
                        {"context": "readiness"},
                    ],
                },
            },
        ],
    }


def validate(branch=None, rulesets=None, status=200, immutable=None):
    return validate_platform_controls(
        branch if branch is not None else protected_branch(),
        rulesets if rulesets is not None else [compliant_ruleset()],
        status,
        {"enabled": True, "enforced_by_owner": False}
        if immutable is None
        else immutable,
        policy(),
    )


def test_cutover_platform_accepts_only_complete_live_controls():
    assert validate() == ()


def test_unprotected_main_blocks_cutover():
    branch = protected_branch()
    branch["protected"] = False
    errors = validate(branch=branch)
    assert "main is not protected" in errors


def test_missing_repository_ruleset_blocks_cutover():
    errors = validate(rulesets=[])
    assert "no active repository ruleset protects the default branch" in errors


def test_ruleset_must_block_deletion_and_force_push():
    ruleset = compliant_ruleset()
    ruleset["rules"] = [
        rule
        for rule in ruleset["rules"]
        if rule["type"] not in {"deletion", "non_fast_forward"}
    ]
    errors = validate(rulesets=[ruleset])
    assert any("deletion" in error and "non_fast_forward" in error for error in errors)


def test_all_three_repository_checks_are_required():
    ruleset = compliant_ruleset()
    status = next(
        rule for rule in ruleset["rules"] if rule["type"] == "required_status_checks"
    )
    status["parameters"]["required_status_checks"] = [{"context": "contract"}]
    errors = validate(rulesets=[ruleset])
    assert any("readiness" in error and "test" in error for error in errors)


def test_required_checks_must_be_strict_and_up_to_date():
    ruleset = compliant_ruleset()
    status = next(
        rule for rule in ruleset["rules"] if rule["type"] == "required_status_checks"
    )
    status["parameters"]["strict_required_status_checks_policy"] = False
    errors = validate(rulesets=[ruleset])
    assert any("strict/up-to-date" in error for error in errors)


def test_bypass_actors_block_cutover():
    ruleset = compliant_ruleset()
    ruleset["bypass_actors"] = [{"actor_id": 5, "actor_type": "RepositoryRole"}]
    errors = validate(rulesets=[ruleset])
    assert any("bypass actors" in error for error in errors)


def test_default_branch_alias_is_accepted():
    ruleset = compliant_ruleset()
    ruleset["conditions"]["ref_name"]["include"] = ["~DEFAULT_BRANCH"]
    assert validate(rulesets=[ruleset]) == ()


def test_immutable_releases_disabled_blocks_cutover():
    errors = validate(status=404, immutable={})
    assert "GitHub immutable releases are disabled" in errors


def test_immutable_release_verification_permission_failure_blocks_cutover():
    errors = validate(status=403, immutable={})
    assert any("could not be verified: HTTP 403" in error for error in errors)


def test_immutable_endpoint_must_return_enabled_true():
    errors = validate(status=200, immutable={"enabled": False})
    assert any("did not return enabled=true" in error for error in errors)


def test_ruleset_excluding_main_is_not_accepted():
    ruleset = copy.deepcopy(compliant_ruleset())
    ruleset["conditions"]["ref_name"]["exclude"] = ["refs/heads/main"]
    errors = validate(rulesets=[ruleset])
    assert "no active repository ruleset protects the default branch" in errors
