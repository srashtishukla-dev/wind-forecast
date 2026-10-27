from datetime import datetime, timedelta, timezone

import pytest

from app.models import ActualRecord, ForecastRecord
from app.services.metrics import calculate_metrics, select_forecasts_for_decision


def _time(hour: int) -> datetime:
    return datetime(2026, 1, 2, hour, tzinfo=timezone.utc)


def test_metrics_use_forecast_minus_actual_convention() -> None:
    actuals = [
        ActualRecord(startTime=_time(0), actualGeneration=100),
        ActualRecord(startTime=_time(1), actualGeneration=200),
    ]
    forecasts = [
        ForecastRecord(
            startTime=_time(0),
            publishTime=_time(0) - timedelta(hours=1),
            forecastGeneration=110,
        ),
        ForecastRecord(
            startTime=_time(1),
            publishTime=_time(1) - timedelta(hours=1),
            forecastGeneration=180,
        ),
    ]

    result = calculate_metrics(actuals, forecasts)

    assert result.mae == pytest.approx(15)
    assert result.rmse == pytest.approx(250**0.5)
    assert result.bias == pytest.approx(-5)
    assert result.matched_observations == 2


def test_metrics_exclude_unmatched_and_missing_observations() -> None:
    actuals = [
        ActualRecord(startTime=_time(0), actualGeneration=100),
        ActualRecord(startTime=_time(1), actualGeneration=None),
        ActualRecord(startTime=_time(2), actualGeneration=200),
    ]
    forecasts = [
        ForecastRecord(
            startTime=_time(0),
            publishTime=_time(0) - timedelta(hours=1),
            forecastGeneration=110,
        ),
        ForecastRecord(
            startTime=_time(1),
            publishTime=_time(1) - timedelta(hours=1),
            forecastGeneration=190,
        ),
        ForecastRecord(
            startTime=_time(3),
            publishTime=_time(3) - timedelta(hours=1),
            forecastGeneration=300,
        ),
    ]

    result = calculate_metrics(actuals, forecasts)

    assert result.matched_observations == 1
    assert result.mae == 10
    assert result.unmatched_actual_records == 1
    assert result.unmatched_forecast_records == 1
    assert result.incomplete_matched_intervals == 1


def test_empty_metrics_return_null_values() -> None:
    result = calculate_metrics([], [])
    assert result.mae is None
    assert result.rmse is None
    assert result.bias is None
    assert result.matched_observations == 0


def test_selection_uses_latest_forecast_at_or_before_cutoff() -> None:
    delivery = _time(12)
    forecasts = [
        ForecastRecord(
            startTime=delivery,
            publishTime=delivery - timedelta(hours=30),
            forecastGeneration=100,
        ),
        ForecastRecord(
            startTime=delivery,
            publishTime=delivery - timedelta(hours=24),
            forecastGeneration=110,
        ),
        ForecastRecord(
            startTime=delivery,
            publishTime=delivery - timedelta(hours=23, minutes=59),
            forecastGeneration=120,
        ),
    ]

    selected = select_forecasts_for_decision(
        forecasts,
        timedelta(hours=24),
    )

    assert len(selected) == 1
    assert selected[0].forecast_generation == 110


def test_forecast_after_cutoff_is_not_selected() -> None:
    delivery = _time(12)
    forecast = ForecastRecord(
        startTime=delivery,
        publishTime=delivery - timedelta(hours=23),
        forecastGeneration=120,
    )

    assert select_forecasts_for_decision(
        [forecast],
        timedelta(hours=24),
    ) == []


def test_selection_rejects_negative_lead() -> None:
    with pytest.raises(ValueError):
        select_forecasts_for_decision([], timedelta(hours=-1))
