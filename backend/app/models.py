"""Validated API and normalized data models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ActualRecord(BaseModel):
    """One normalized FUELHH wind generation observation."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    start_time: datetime = Field(alias="startTime")
    actual_generation: float | None = Field(alias="actualGeneration")

    @field_validator("start_time")
    @classmethod
    def normalize_start_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("startTime must include a timezone")
        return value.astimezone(timezone.utc)


class ForecastRecord(BaseModel):
    """One normalized WINDFOR forecast version."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    start_time: datetime = Field(alias="startTime")
    publish_time: datetime = Field(alias="publishTime")
    forecast_generation: float | None = Field(alias="forecastGeneration")

    @field_validator("start_time", "publish_time")
    @classmethod
    def normalize_times(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must include a timezone")
        return value.astimezone(timezone.utc)


class DataQuality(BaseModel):
    """Counts of source rows that could not be fully normalized."""

    invalid_timestamp_records: int = 0
    missing_generation_records: int = 0
    invalid_generation_records: int = 0


class ActualsResponse(BaseModel):
    """Actual records and their data-quality summary."""

    records: list[ActualRecord]
    incomplete_intervals: int
    quality: DataQuality


class ForecastsResponse(BaseModel):
    """Forecast versions and their data-quality summary."""

    records: list[ForecastRecord]
    incomplete_intervals: int
    quality: DataQuality


class ExcludedRecords(BaseModel):
    """Counts of observations that could not contribute to accuracy metrics."""

    unmatched_actual_records: int
    unmatched_forecast_records: int
    incomplete_matched_intervals: int
    invalid_actual_timestamps: int
    invalid_forecast_timestamps: int
    invalid_actual_generations: int
    invalid_forecast_generations: int


class ForecastAccuracyResponse(BaseModel):
    """Accuracy metrics in the source generation units."""

    mae: float | None
    rmse: float | None
    bias: float | None
    units: Literal["Elexon generation units"] = "Elexon generation units"
    matched_observations: int
    actual_records: list[ActualRecord]
    selected_forecasts: list[ForecastRecord]
    excluded_records: ExcludedRecords
    decision_lead_hours: float
    publication_window_start: datetime
    publication_window_end: datetime


class ForecastVersionsResponse(BaseModel):
    """All available versions in a requested delivery and publication window."""

    start_time: datetime
    records: list[ForecastRecord]
    incomplete_intervals: int
    quality: DataQuality
