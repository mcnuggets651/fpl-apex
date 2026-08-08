import pandas as pd
import pytest

from apex_fpl.data.core_insights import FPLCoreClient


def test_stable_identity_rows_deduplicates_identical_rows() -> None:
    rows = pd.DataFrame(
        {
            "player_code": [101, 101, 202],
            "player_id": [1, 1, 2],
        }
    )

    result = FPLCoreClient._stable_identity_rows(rows, "test")

    assert result.to_dict("records") == [
        {"player_code": 101, "player_id": 1},
        {"player_code": 202, "player_id": 2},
    ]


def test_stable_identity_rows_rejects_conflicting_code_mapping() -> None:
    rows = pd.DataFrame(
        {
            "player_code": [101, 101],
            "player_id": [1, 2],
        }
    )

    with pytest.raises(ValueError, match="conflicting player_code mappings"):
        FPLCoreClient._stable_identity_rows(rows, "test")


def test_stable_identity_rows_rejects_conflicting_id_mapping() -> None:
    rows = pd.DataFrame(
        {
            "player_code": [101, 202],
            "player_id": [1, 1],
        }
    )

    with pytest.raises(ValueError, match="conflicting player_id mappings"):
        FPLCoreClient._stable_identity_rows(rows, "test")
