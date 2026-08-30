from __future__ import annotations

import base64
from datetime import datetime, timezone

from apex.runtime.publication import verify_commitment


def _utc(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def verify_private_reveal(
    *,
    reveal: dict,
    commitment: dict,
    key: bytes,
    public_attempt: dict,
    now: str | datetime | None = None,
) -> bool:
    """Verify crypto, attempt identity and deadline before revealing a decision.

    HMAC validity alone is intentionally insufficient. A reveal is valid only
    when it belongs to the exact public attempt that carried the commitment and
    the public contract's reveal-not-before timestamp has passed.
    """

    if len(key) != 32:
        return False
    if commitment.get("algorithm") != "HMAC-SHA256":
        return False
    if commitment.get("domain") != "apex-v2-private-decision-v1":
        return False

    public_attempt_id = str(public_attempt.get("public_attempt_id") or "")
    if not public_attempt_id:
        return False
    if str(reveal.get("public_attempt_id") or "") != public_attempt_id:
        return False
    if str(commitment.get("public_attempt_id") or "") != public_attempt_id:
        return False

    for field in ("season", "target_gameweek"):
        if reveal.get(field) != public_attempt.get(field):
            return False

    reveal_not_before = commitment.get("reveal_not_before")
    if not reveal_not_before:
        return False
    current = _utc(now or datetime.now(timezone.utc))
    if current < _utc(reveal_not_before):
        return False

    return verify_commitment(reveal, commitment, key)


def verify_private_payload_reveal(
    *,
    private_payload: dict,
    public_attempt: dict,
    now: str | datetime | None = None,
) -> bool:
    """Verify a stored private payload against its public commitment."""

    commitment = public_attempt.get("private_decision_commitment")
    reveal = private_payload.get("reveal_record")
    encoded_key = private_payload.get("commitment_key_b64")
    if not isinstance(commitment, dict) or not isinstance(reveal, dict):
        return False
    if not encoded_key:
        return False
    try:
        key = base64.b64decode(str(encoded_key), validate=True)
    except Exception:
        return False
    if private_payload.get("public_attempt_id") != public_attempt.get(
        "public_attempt_id"
    ):
        return False
    return verify_private_reveal(
        reveal=reveal,
        commitment=commitment,
        key=key,
        public_attempt=public_attempt,
        now=now,
    )
