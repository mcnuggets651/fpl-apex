from __future__ import annotations

import json

import numpy as np

from apex_fpl.services.provenance import SourceStatus


def test_source_status_normalises_numpy_booleans_to_native_json_bools() -> None:
    status = SourceStatus(
        name="fpl_core_previous_season",
        ok=np.bool_(True),
        configured=np.bool_(True),
        detail="prior playing-time coverage=80.2%",
    )

    payload = status.to_dict()

    assert payload["ok"] is True
    assert payload["configured"] is True

    roundtrip = json.loads(json.dumps(payload))
    assert roundtrip["ok"] is True
    assert roundtrip["configured"] is True


def test_source_status_preserves_false_bool_like_values() -> None:
    status = SourceStatus(
        name="example",
        ok=np.bool_(False),
        configured=np.bool_(False),
    )

    payload = status.to_dict()

    assert payload["ok"] is False
    assert payload["configured"] is False
