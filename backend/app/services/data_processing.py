"""Timestamp, value, and duplicate handling for Elexon records."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from app.models import ActualRecord, DataQuality, ForecastRecord


class DataProcessingError(ValueError):
    """Raised when source rows contain conflicting duplicate observations."""


@dataclass(frozen=True)
class NormalizedActuals:
    records: list[ActualRecord]
    quality: DataQuality
    invalid_generation_times: frozenset[datetime]


@dataclass(frozen=True)
class NormalizedForecasts:
    records: list[ForecastRecord]
    quality: DataQuality
    invalid_generation_versions: frozenset[tuple[datetime, datetime]]


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _parse_generation(value: Any) -> tuple[float | None, str]:
    if value is None or value == "":
        return None, "missing"
    if isinstance(value, bool):
        return None, "invalid"
    try:
        generation = float(value)
    except (TypeError, ValueError):
        return None, "invalid"
    if not math.isfinite(generation):
        return None, "invalid"
    return generation, "valid"


def _quality(
    invalid_timestamps: int,
    generation_statuses: list[str],
) -> DataQuality:
    return DataQuality(
        invalid_timestamp_records=invalid_timestamps,
        missing_generation_records=generation_statuses.count("missing"),
        invalid_generation_records=generation_statuses.count("invalid"),
    )


def normalize_actual_records(rows: list[Mapping[str, Any]]) -> NormalizedActuals:
    """Keep WIND actuals, normalize timestamps/values, and deduplicate by interval."""
    invalid_timestamps = 0
    candidates: dict[datetime, tuple[ActualRecord, datetime | None, str]] = {}

    for row in rows:
        if row.get("fuelType") != "WIND":
            continue
        start_time = _parse_timestamp(row.get("startTime"))
        if start_time is None:
            invalid_timestamps += 1
            continue
        generation, status = _parse_generation(row.get("generation"))
        publish_time = _parse_timestamp(row.get("publishTime"))
        record = ActualRecord(
            startTime=start_time,
            actualGeneration=generation,
        )
        existing = candidates.get(start_time)
        if existing is None:
            candidates[start_time] = (record, publish_time, status)
            continue

        existing_record, existing_publish, _ = existing
        if publish_time is not None and (
            existing_publish is None or publish_time > existing_publish
        ):
            candidates[start_time] = (record, publish_time, status)
        elif publish_time == existing_publish:
            if record.actual_generation != existing_record.actual_generation:
                raise DataProcessingError(
                    f"Conflicting FUELHH values for {start_time.isoformat()} "
                    "at the same publication time"
                )

    ordered = sorted(candidates.values(), key=lambda candidate: candidate[0].start_time)
    records = [candidate[0] for candidate in ordered]
    statuses = [candidate[2] for candidate in ordered]
    return NormalizedActuals(
        records=records,
        quality=_quality(invalid_timestamps, statuses),
        invalid_generation_times=frozenset(
            candidate[0].start_time
            for candidate in ordered
            if candidate[2] == "invalid"
        ),
    )


def normalize_forecast_records(rows: list[Mapping[str, Any]]) -> NormalizedForecasts:
    """Normalize forecast versions and remove exact duplicates without collapsing vintages."""
    invalid_timestamps = 0
    candidates: dict[
        tuple[datetime, datetime],
        tuple[ForecastRecord, str],
    ] = {}

    for row in rows:
        start_time = _parse_timestamp(row.get("startTime"))
        publish_time = _parse_timestamp(row.get("publishTime"))
        if start_time is None or publish_time is None:
            invalid_timestamps += 1
            continue
        generation, status = _parse_generation(row.get("generation"))
        record = ForecastRecord(
            startTime=start_time,
            publishTime=publish_time,
            forecastGeneration=generation,
        )
        key = (start_time, publish_time)
        existing = candidates.get(key)
        if existing is not None:
            if existing[0].forecast_generation != record.forecast_generation:
                raise DataProcessingError(
                    "Conflicting WINDFOR values for "
                    f"{start_time.isoformat()} published at {publish_time.isoformat()}"
                )
            continue
        candidates[key] = (record, status)

    ordered = sorted(
        candidates.values(),
        key=lambda candidate: (candidate[0].start_time, candidate[0].publish_time),
    )
    return NormalizedForecasts(
        records=[candidate[0] for candidate in ordered],
        quality=_quality(
            invalid_timestamps,
            [candidate[1] for candidate in ordered],
        ),
        invalid_generation_versions=frozenset(
            (candidate[0].start_time, candidate[0].publish_time)
            for candidate in ordered
            if candidate[1] == "invalid"
        ),
    )
