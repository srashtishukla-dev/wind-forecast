"""Forecast selection and accuracy calculations."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from app.models import ActualRecord, ForecastRecord


@dataclass(frozen=True)
class AccuracyMetrics:
    mae: float | None
    rmse: float | None
    bias: float | None
    matched_observations: int
    unmatched_actual_records: int
    unmatched_forecast_records: int
    incomplete_matched_intervals: int


def select_forecasts_for_decision(
    forecasts: Sequence[ForecastRecord],
    decision_lead: timedelta = timedelta(hours=24),
) -> list[ForecastRecord]:
    """Choose the latest publication no later than delivery start minus the lead time."""
    if decision_lead < timedelta(0):
        raise ValueError("decision_lead cannot be negative")

    latest_by_delivery: dict[
        datetime,
        ForecastRecord,
    ] = {}
    for forecast in forecasts:
        cutoff = forecast.start_time - decision_lead
        if forecast.publish_time > cutoff:
            continue
        previous = latest_by_delivery.get(forecast.start_time)
        if previous is None or forecast.publish_time > previous.publish_time:
            latest_by_delivery[forecast.start_time] = forecast
    return sorted(latest_by_delivery.values(), key=lambda item: item.start_time)


def calculate_metrics(
    actuals: Sequence[ActualRecord],
    forecasts: Sequence[ForecastRecord],
) -> AccuracyMetrics:
    """Calculate MAE, RMSE, and forecast-minus-actual bias for matched intervals."""
    actual_by_time: dict[datetime, ActualRecord] = {}
    forecast_by_time: dict[datetime, ForecastRecord] = {}
    for actual in actuals:
        if actual.start_time in actual_by_time:
            raise ValueError("actuals must contain at most one record per delivery interval")
        actual_by_time[actual.start_time] = actual
    for forecast in forecasts:
        if forecast.start_time in forecast_by_time:
            raise ValueError(
                "forecasts must be selected to one record per delivery interval"
            )
        forecast_by_time[forecast.start_time] = forecast

    actual_times = set(actual_by_time)
    forecast_times = set(forecast_by_time)
    common_times = actual_times & forecast_times
    unmatched_actual = len(actual_times - forecast_times)
    unmatched_forecast = len(forecast_times - actual_times)
    errors: list[float] = []
    incomplete = 0
    for delivery_time in common_times:
        actual_generation = actual_by_time[delivery_time].actual_generation
        forecast_generation = forecast_by_time[delivery_time].forecast_generation
        if actual_generation is None or forecast_generation is None:
            incomplete += 1
            continue
        error = forecast_generation - actual_generation
        if not math.isfinite(error):
            incomplete += 1
            continue
        errors.append(error)

    if not errors:
        return AccuracyMetrics(
            mae=None,
            rmse=None,
            bias=None,
            matched_observations=0,
            unmatched_actual_records=unmatched_actual,
            unmatched_forecast_records=unmatched_forecast,
            incomplete_matched_intervals=incomplete,
        )

    count = len(errors)
    return AccuracyMetrics(
        mae=math.fsum(abs(error) for error in errors) / count,
        rmse=math.sqrt(math.fsum(error * error for error in errors) / count),
        bias=math.fsum(errors) / count,
        matched_observations=count,
        unmatched_actual_records=unmatched_actual,
        unmatched_forecast_records=unmatched_forecast,
        incomplete_matched_intervals=incomplete,
    )
