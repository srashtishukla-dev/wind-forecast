"""HTTP client for the documented Elexon BMRS streaming endpoints."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.config import Settings

_UK_TIMEZONE = ZoneInfo("Europe/London")


class ElexonAPIError(RuntimeError):
    """Raised when the Elexon API cannot provide a valid response."""


class ElexonClient:
    """Bounded HTTP client for FUELHH and WINDFOR."""

    _TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings.validated()
        self._client = httpx.Client(
            timeout=settings.elexon_request_timeout_seconds,
            transport=transport,
            headers={"Accept": "application/json"},
        )

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def get_actuals(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """Fetch FUELHH rows for the UTC delivery window, filtered to wind."""
        start_utc, end_utc = self._validate_window(start, end, "delivery")
        last_included = end_utc - timedelta(microseconds=1)
        params = {
            "settlementDateFrom": start_utc.astimezone(_UK_TIMEZONE).date().isoformat(),
            "settlementDateTo": last_included.astimezone(_UK_TIMEZONE).date().isoformat(),
            "fuelType": "WIND",
        }
        return self._get_stream("/datasets/FUELHH/stream", params)

    def get_forecasts(
        self,
        publish_from: datetime,
        publish_to: datetime,
    ) -> list[dict[str, Any]]:
        """Fetch WINDFOR rows by the documented publication-time filters."""
        publish_start, publish_end = self._validate_window(
            publish_from,
            publish_to,
            "publication",
        )
        params = {
            "publishDateTimeFrom": publish_start.isoformat().replace("+00:00", "Z"),
            "publishDateTimeTo": publish_end.isoformat().replace("+00:00", "Z"),
        }
        return self._get_stream("/datasets/WINDFOR/stream", params)

    def _validate_window(
        self,
        start: datetime,
        end: datetime,
        name: str,
    ) -> tuple[datetime, datetime]:
        if start.tzinfo is None or start.utcoffset() is None:
            raise ValueError(f"{name} start must include a timezone")
        if end.tzinfo is None or end.utcoffset() is None:
            raise ValueError(f"{name} end must include a timezone")
        start_utc = start.astimezone(timezone.utc)
        end_utc = end.astimezone(timezone.utc)
        if start_utc >= end_utc:
            raise ValueError(f"{name} start must be earlier than end")
        if end_utc - start_utc > timedelta(days=self._settings.max_query_range_days):
            raise ValueError(
                f"{name} window cannot exceed "
                f"{self._settings.max_query_range_days} days"
            )
        return start_utc, end_utc

    def _get_stream(
        self,
        path: str,
        params: dict[str, str],
    ) -> list[dict[str, Any]]:
        url = f"{self._settings.elexon_api_base_url}{path}"
        for attempt in range(self._settings.elexon_retry_count + 1):
            try:
                with self._client.stream("GET", url, params=params) as response:
                    if response.status_code in self._TRANSIENT_STATUS_CODES:
                        if attempt < self._settings.elexon_retry_count:
                            time.sleep(0.1 * (2**attempt))
                            continue
                        raise ElexonAPIError(
                            f"Elexon API returned HTTP {response.status_code} "
                            "after retries"
                        )
                    if response.is_error:
                        raise ElexonAPIError(
                            f"Elexon API returned HTTP {response.status_code}"
                        )

                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > self._settings.max_response_bytes:
                            raise ElexonAPIError(
                                "Elexon API response exceeds the configured size limit"
                            )

                try:
                    data = json.loads(body)
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise ElexonAPIError("Elexon API returned invalid JSON") from exc
                if not isinstance(data, list):
                    raise ElexonAPIError(
                        "Elexon API returned an unexpected response; expected a JSON array"
                    )
                if any(not isinstance(item, dict) for item in data):
                    raise ElexonAPIError(
                        "Elexon API returned an invalid row; expected JSON objects"
                    )
                return data
            except ElexonAPIError:
                raise
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= self._settings.elexon_retry_count:
                    raise ElexonAPIError(
                        f"Elexon API request failed after {attempt + 1} attempts: {exc}"
                    ) from exc
                time.sleep(0.1 * (2**attempt))
        raise ElexonAPIError("Elexon API request failed without a response")
