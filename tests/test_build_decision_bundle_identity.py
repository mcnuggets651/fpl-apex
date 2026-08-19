from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


def _load_identity_alias_helper():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "build_decision_bundle.py"
    spec = importlib.util.spec_from_file_location("apex_build_decision_bundle", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._with_official_identity_aliases


_with_official_identity_aliases = _load_identity_alias_helper()


def test_sealed_surface_retains_exact_official_full_name_aliases() -> None:
    projected = pd.DataFrame(
        [
            {"player_id": 1, "web_name": "Raya", "gw1_xp": 4.5},
            {"player_id": 2, "web_name": "Gabriel", "gw1_xp": 5.0},
        ]
    )
    official = pd.DataFrame(
        [
            {
                "player_id": 1,
                "web_name": "Raya",
                "first_name": "David",
                "second_name": "Raya Martín",
            },
            {
                "player_id": 2,
                "web_name": "Gabriel",
                "first_name": "Gabriel",
                "second_name": "dos Santos Magalhães",
            },
        ]
    )

    sealed = _with_official_identity_aliases(projected, official)

    assert sealed.loc[sealed.player_id.eq(1), "first_name"].item() == "David"
    assert sealed.loc[sealed.player_id.eq(1), "second_name"].item() == "Raya Martín"
    assert (
        sealed.loc[sealed.player_id.eq(2), "first_name"].item()
        + " "
        + sealed.loc[sealed.player_id.eq(2), "second_name"].item()
        == "Gabriel dos Santos Magalhães"
    )


def test_sealed_surface_rejects_player_id_absent_from_official_registry() -> None:
    projected = pd.DataFrame([{"player_id": 999, "web_name": "Wrong"}])
    official = pd.DataFrame(
        [
            {
                "player_id": 1,
                "first_name": "David",
                "second_name": "Raya Martín",
            }
        ]
    )

    with pytest.raises(ValueError, match="IDs absent from Official FPL"):
        _with_official_identity_aliases(projected, official)


def test_sealed_surface_rejects_duplicate_official_ids() -> None:
    projected = pd.DataFrame([{"player_id": 1, "web_name": "Raya"}])
    official = pd.DataFrame(
        [
            {"player_id": 1, "first_name": "David", "second_name": "Raya Martín"},
            {"player_id": 1, "first_name": "David", "second_name": "Raya Martín"},
        ]
    )

    with pytest.raises(ValueError, match="duplicate player IDs"):
        _with_official_identity_aliases(projected, official)
