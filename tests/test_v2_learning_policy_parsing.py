from __future__ import annotations

import pytest

from apex_fpl.control.learning_policy_registry import load_learning_policy_registry_bytes


def test_learning_policy_yaml_rejects_string_boolean_laundering() -> None:
    payload = b"""\
schema_version: 1
season: 2026-2027
champion_policy_id: null
policies:
  - policy_name: shadow-policy
    policy_version: v1
    qualification_state: SHADOW
    qualification_artifact_id: null
    promotion_rule_artifact_id: null
    first_available_at: '2026-08-01T00:00:00Z'
    valid_seasons: ['2026-2027']
    requirements:
      - metric: MINUTES_MAE
        target: MINUTES
        cohort: ALL
        minimum_cases: 2
        require_interval: 'false'
    promotion_rules: []
"""
    with pytest.raises(ValueError, match="require_interval must be boolean"):
        load_learning_policy_registry_bytes(payload)


def test_learning_policy_yaml_rejects_string_promotion_boolean_laundering() -> None:
    payload = b"""\
schema_version: 1
season: 2026-2027
champion_policy_id: null
policies:
  - policy_name: shadow-policy
    policy_version: v1
    qualification_state: SHADOW
    qualification_artifact_id: null
    promotion_rule_artifact_id: null
    first_available_at: '2026-08-01T00:00:00Z'
    valid_seasons: ['2026-2027']
    requirements:
      - metric: MINUTES_MAE
        target: MINUTES
        cohort: ALL
        minimum_cases: 2
        require_interval: false
    promotion_rules:
      - metric: MINUTES_MAE
        target: MINUTES
        cohort: ALL
        direction: LOWER_IS_BETTER
        minimum_improvement: {numerator: 1, denominator: 1}
        require_interval_superiority: 'false'
"""
    with pytest.raises(ValueError, match="require_interval_superiority must be boolean"):
        load_learning_policy_registry_bytes(payload)
