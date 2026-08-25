"""Dependency-free numeric policy identity shared by V2 decision contracts."""

from __future__ import annotations


DECISION_NUMERIC_POLICY_ID = "decision-rational-v1"


def require_decision_numeric_policy(value: str) -> str:
    """Return the canonical numeric policy or fail closed on unsupported semantics."""

    text = str(value).strip()
    if text != DECISION_NUMERIC_POLICY_ID:
        raise ValueError(
            "unsupported V2 decision numeric policy: "
            f"{text!r}; expected {DECISION_NUMERIC_POLICY_ID!r}"
        )
    return text
