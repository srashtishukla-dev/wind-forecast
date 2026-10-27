"""FastAPI routes for wind generation and forecast analytics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.config import Settings
from app.models import (
    ActualRecord,
    ActualsResponse,
    DataQuality,
    ExcludedRecords,
    ForecastAccuracyResponse,
    ForecastRecord,
    ForecastVersionsResponse,
    ForecastsResponse,
)
from app.services.data_processing import (
    DataProcessingError,
    NormalizedActuals,
    NormalizedForecasts,
    normalize_actual_records,
    normalize_forecast_records,
)
from app.services.elexon_client import ElexonClient
from app.services.metrics import calculate_metrics, select_forecasts_for_decision

router = APIRouter()


def get_elexon_client(request: Request) -> ElexonClient:
    """Return the client held by the application lifespan."""
    return request.app.state.elexon_client


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _validate_time(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(
            status_code=422,
            detail=f"{name} must include a timezone, for example 2026-01-01T00:00:00Z",
        )
    return value.astimezone(timezone.utc)


def _validate_window(
    start: datetime,
    end: datetime,
    name: str,
    max_days: int,
) -> tuple[datetime, datetime]:
    start_utc = _validate_time(start, f"{name}_from")
    end_utc = _validate_time(end, f"{name}_to")
    if start_utc >= end_utc:
        raise HTTPException(
            status_code=422,
            detail=f"{name}_from must be earlier than {name}_to",
        )
    if end_utc - start_utc > timedelta(days=max_days):
        raise HTTPException(
            status_code=422,
            detail=f"{name} window cannot exceed {max_days} days",
        )
    return start_utc, end_utc


def _filter_delivery_window(
    records: list[ForecastRecord],
    start: datetime | None,
    end: datetime | None,
    max_days: int,
) -> list[ForecastRecord]:
    if (start is None) != (end is None):
        raise HTTPException(
            status_code=422,
            detail="start_time and end_time must be supplied together",
        )
    if start is None or end is None:
        return records
    start_utc, end_utc = _validate_window(start, end, "delivery", max_days)
    return [
        record
        for record in records
        if start_utc <= record.start_time < end_utc
    ]


def _incomplete_count(records: list[ActualRecord | ForecastRecord]) -> int:
    return sum(
        1
        for record in records
        if (
            record.actual_generation is None
            if isinstance(record, ActualRecord)
            else record.forecast_generation is None
        )
    )


def _actual_quality(
    normalized: NormalizedActuals,
    records: list[ActualRecord],
) -> DataQuality:
    invalid_times = normalized.invalid_generation_times
    return DataQuality(
        invalid_timestamp_records=normalized.quality.invalid_timestamp_records,
        missing_generation_records=sum(
            record.actual_generation is None and record.start_time not in invalid_times
            for record in records
        ),
        invalid_generation_records=sum(
            record.start_time in invalid_times for record in records
        ),
    )


def _forecast_quality(
    normalized: NormalizedForecasts,
    records: list[ForecastRecord],
) -> DataQuality:
    invalid_versions = normalized.invalid_generation_versions
    return DataQuality(
        invalid_timestamp_records=normalized.quality.invalid_timestamp_records,
        missing_generation_records=sum(
            record.forecast_generation is None
            and (record.start_time, record.publish_time) not in invalid_versions
            for record in records
        ),
        invalid_generation_records=sum(
            (record.start_time, record.publish_time) in invalid_versions
            for record in records
        ),
    )


@router.get("/health")
def health() -> dict[str, str]:
    """Return the process health status without contacting Elexon."""
    return {"status": "ok"}


@router.get("/api/actuals", response_model=ActualsResponse)
def get_actuals(
    request: Request,
    start_time: datetime = Query(..., description="Inclusive UTC delivery start"),
    end_time: datetime = Query(..., description="Exclusive UTC delivery end"),
    client: ElexonClient = Depends(get_elexon_client),
) -> ActualsResponse:
    """Fetch actual wind generation for the bounded delivery interval."""
    settings = _settings(request)
    start, end = _validate_window(
        start_time,
        end_time,
        "delivery",
        settings.max_query_range_days,
    )
    normalized = normalize_actual_records(client.get_actuals(start, end))
    records = [
        record
        for record in normalized.records
        if start <= record.start_time < end
    ]
    return ActualsResponse(
        records=records,
        incomplete_intervals=_incomplete_count(records),
        quality=_actual_quality(normalized, records),
    )


@router.get("/api/forecasts", response_model=ForecastsResponse)
def get_forecasts(
    request: Request,
    publish_from: datetime = Query(..., description="Inclusive forecast publication time"),
    publish_to: datetime = Query(..., description="Exclusive forecast publication time"),
    start_time: datetime | None = Query(
        default=None,
        description="Optional inclusive delivery start filter",
    ),
    end_time: datetime | None = Query(
        default=None,
        description="Optional exclusive delivery end filter",
    ),
    client: ElexonClient = Depends(get_elexon_client),
) -> ForecastsResponse:
    """Fetch forecast versions in a publication window, optionally filtering delivery time."""
    settings = _settings(request)
    publish_start, publish_end = _validate_window(
        publish_from,
        publish_to,
        "publication",
        settings.max_query_range_days,
    )
    normalized = normalize_forecast_records(
        client.get_forecasts(publish_start, publish_end)
    )
    publication_records = [
        record
        for record in normalized.records
        if publish_start <= record.publish_time < publish_end
    ]
    records = _filter_delivery_window(
        publication_records,
        start_time,
        end_time,
        settings.max_query_range_days,
    )
    return ForecastsResponse(
        records=records,
        incomplete_intervals=_incomplete_count(records),
        quality=_forecast_quality(normalized, records),
    )


@router.get("/api/forecast-accuracy", response_model=ForecastAccuracyResponse)
def get_forecast_accuracy(
    request: Request,
    start_time: datetime = Query(..., description="Inclusive delivery-period start"),
    end_time: datetime = Query(..., description="Exclusive delivery-period end"),
    publish_from: datetime = Query(..., description="Inclusive forecast publication window"),
    publish_to: datetime = Query(..., description="Exclusive forecast publication window"),
    decision_lead_hours: float | None = Query(
        default=None,
        ge=0,
        le=720,
        description=(
            "Forecast cutoff lead before delivery start. Defaults to DECISION_LEAD_HOURS "
            "(24 hours); this is an assignment policy, not an official market deadline."
        ),
    ),
    client: ElexonClient = Depends(get_elexon_client),
) -> ForecastAccuracyResponse:
    """Calculate accuracy using only forecasts published before each decision cutoff."""
    settings = _settings(request)
    delivery_start, delivery_end = _validate_window(
        start_time,
        end_time,
        "delivery",
        settings.max_query_range_days,
    )
    publish_start, publish_end = _validate_window(
        publish_from,
        publish_to,
        "publication",
        settings.max_query_range_days,
    )
    lead_hours = (
        settings.decision_lead_hours
        if decision_lead_hours is None
        else decision_lead_hours
    )
    if lead_hours < 0:
        raise HTTPException(
            status_code=422,
            detail="decision_lead_hours cannot be negative",
        )

    normalized_actuals = normalize_actual_records(
        client.get_actuals(delivery_start, delivery_end)
    )
    actual_data_records = [
        record
        for record in normalized_actuals.records
        if delivery_start <= record.start_time < delivery_end
    ]
    forecast_data = normalize_forecast_records(
        client.get_forecasts(publish_start, publish_end)
    )
    delivery_forecasts = [
        record
        for record in forecast_data.records
        if publish_start <= record.publish_time < publish_end
        and delivery_start <= record.start_time < delivery_end
    ]
    selected = select_forecasts_for_decision(
        delivery_forecasts,
        timedelta(hours=lead_hours),
    )
    metrics = calculate_metrics(actual_data_records, selected)
    return ForecastAccuracyResponse(
        mae=metrics.mae,
        rmse=metrics.rmse,
        bias=metrics.bias,
        matched_observations=metrics.matched_observations,
        actual_records=actual_data_records,
        selected_forecasts=selected,
        excluded_records=ExcludedRecords(
            unmatched_actual_records=metrics.unmatched_actual_records,
            unmatched_forecast_records=metrics.unmatched_forecast_records,
            incomplete_matched_intervals=metrics.incomplete_matched_intervals,
            invalid_actual_timestamps=normalized_actuals.quality.invalid_timestamp_records,
            invalid_forecast_timestamps=forecast_data.quality.invalid_timestamp_records,
            invalid_actual_generations=_actual_quality(
                normalized_actuals,
                actual_data_records,
            ).invalid_generation_records,
            invalid_forecast_generations=_forecast_quality(
                forecast_data,
                selected,
            ).invalid_generation_records,
        ),
        decision_lead_hours=lead_hours,
        publication_window_start=publish_start,
        publication_window_end=publish_end,
    )


@router.get("/api/forecast-versions", response_model=ForecastVersionsResponse)
def get_forecast_versions(
    request: Request,
    start_time: datetime = Query(..., description="Exact delivery interval start"),
    publish_from: datetime = Query(..., description="Inclusive forecast publication time"),
    publish_to: datetime = Query(..., description="Exclusive forecast publication time"),
    client: ElexonClient = Depends(get_elexon_client),
) -> ForecastVersionsResponse:
    """Return every available publication for one delivery interval."""
    settings = _settings(request)
    delivery_time = _validate_time(start_time, "start_time")
    publish_start, publish_end = _validate_window(
        publish_from,
        publish_to,
        "publication",
        settings.max_query_range_days,
    )
    normalized = normalize_forecast_records(
        client.get_forecasts(publish_start, publish_end)
    )
    versions = sorted(
        (
            record
            for record in normalized.records
            if record.start_time == delivery_time
            and publish_start <= record.publish_time < publish_end
        ),
        key=lambda record: record.publish_time,
    )
    return ForecastVersionsResponse(
        start_time=delivery_time,
        records=versions,
        incomplete_intervals=_incomplete_count(versions),
        quality=_forecast_quality(normalized, versions),
    )
