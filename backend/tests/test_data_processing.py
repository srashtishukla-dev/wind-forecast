from datetime import datetime, timezone

import pytest

from app.services.data_processing import (
    DataProcessingError,
    normalize_actual_records,
    normalize_forecast_records,
)


def test_actuals_filter_wind_normalize_and_keep_missing_generation() -> None:
    result = normalize_actual_records(
        [
            {
                "fuelType": "WIND",
                "startTime": "2026-01-01T00:00:00+00:00",
                "generation": "12.5",
                "publishTime": "2026-01-01T00:30:00Z",
            },
            {
                "fuelType": "CCGT",
                "startTime": "2026-01-01T00:00:00Z",
                "generation": 99,
            },
            {
                "fuelType": "WIND",
                "startTime": "2026-01-01T00:30:00Z",
                "generation": None,
            },
            {
                "fuelType": "WIND",
                "startTime": "not-a-time",
                "generation": 1,
            },
        ]
    )

    assert len(result.records) == 2
    assert result.records[0].start_time == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert result.records[0].actual_generation == 12.5
    assert result.records[1].actual_generation is None
    assert result.quality.invalid_timestamp_records == 1
    assert result.quality.missing_generation_records == 1


def test_actual_duplicate_uses_latest_publication() -> None:
    result = normalize_actual_records(
        [
            {
                "fuelType": "WIND",
                "startTime": "2026-01-01T00:00:00Z",
                "publishTime": "2026-01-01T00:30:00Z",
                "generation": 100,
            },
            {
                "fuelType": "WIND",
                "startTime": "2026-01-01T00:00:00Z",
                "publishTime": "2026-01-01T01:00:00Z",
                "generation": 101,
            },
        ]
    )

    assert len(result.records) == 1
    assert result.records[0].actual_generation == 101


def test_conflicting_actuals_at_same_publication_are_rejected() -> None:
    rows = [
        {
            "fuelType": "WIND",
            "startTime": "2026-01-01T00:00:00Z",
            "publishTime": "2026-01-01T00:30:00Z",
            "generation": value,
        }
        for value in (100, 101)
    ]
    with pytest.raises(DataProcessingError):
        normalize_actual_records(rows)


def test_forecast_versions_are_preserved_sorted_and_exact_duplicates_removed() -> None:
    row = {
        "startTime": "2026-01-02T00:00:00Z",
        "publishTime": "2026-01-01T00:00:00Z",
        "generation": 120,
    }
    result = normalize_forecast_records(
        [
            {**row, "publishTime": "2025-12-31T23:00:00Z"},
            row,
            row,
        ]
    )

    assert len(result.records) == 2
    assert result.records[0].publish_time < result.records[1].publish_time
    assert result.records[1].forecast_generation == 120


def test_conflicting_forecast_versions_with_same_timestamp_are_rejected() -> None:
    rows = [
        {
            "startTime": "2026-01-02T00:00:00Z",
            "publishTime": "2026-01-01T00:00:00Z",
            "generation": value,
        }
        for value in (120, 121)
    ]
    with pytest.raises(DataProcessingError):
        normalize_forecast_records(rows)


def test_invalid_generation_is_preserved_as_missing_not_zero() -> None:
    result = normalize_forecast_records(
        [
            {
                "startTime": "2026-01-02T00:00:00Z",
                "publishTime": "2026-01-01T00:00:00Z",
                "generation": "NaN",
            }
        ]
    )
    assert result.records[0].forecast_generation is None
    assert result.quality.invalid_generation_records == 1


def test_empty_datasets_are_safe() -> None:
    assert normalize_actual_records([]).records == []
    assert normalize_forecast_records([]).records == []
