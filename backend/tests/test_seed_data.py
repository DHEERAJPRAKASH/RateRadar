"""Tests for the seed_data management command helpers."""

from ingestion.management.commands.seed_data import _rows_from_dict


def test_rows_from_dict_converts_columnar_batch_to_rows():
    batch = {
        "provider": ["HSBC", "Chase"],
        "rate_type": ["savings", "checking"],
        "rate_value": [4.5, 1.2],
    }

    rows = list(_rows_from_dict(batch))

    assert rows == [
        {"provider": "HSBC", "rate_type": "savings", "rate_value": 4.5},
        {"provider": "Chase", "rate_type": "checking", "rate_value": 1.2},
    ]
