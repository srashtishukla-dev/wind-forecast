import json
from datetime import datetime, timezone

import httpx
import pytest

from app.config import Settings
from app.services.elexon_client import ElexonAPIError, ElexonClient


def _settings(**overrides: object) -> Settings:
    values = {
        "elexon_api_base_url": "https://elexon.test/bmrs/api/v1",
        "elexon_retry_count": 0,
    }
    values.update(overrides)
    return Settings(**values).validated()


def test_actual_request_uses_documented_date_and_wind_filters() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[])

    client = ElexonClient(_settings(), httpx.MockTransport(handler))
    try:
        result = client.get_actuals(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
    finally:
        client.close()

    assert result == []
    assert requests[0].url.path.endswith("/datasets/FUELHH/stream")
    assert requests[0].url.params["settlementDateFrom"] == "2026-01-01"
    assert requests[0].url.params["settlementDateTo"] == "2026-01-01"
    assert requests[0].url.params["fuelType"] == "WIND"


def test_actual_settlement_dates_use_uk_local_calendar() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[])

    client = ElexonClient(_settings(), httpx.MockTransport(handler))
    try:
        client.get_actuals(
            datetime(2026, 7, 1, 23, 30, tzinfo=timezone.utc),
            datetime(2026, 7, 2, 0, 30, tzinfo=timezone.utc),
        )
    finally:
        client.close()

    assert requests[0].url.params["settlementDateFrom"] == "2026-07-02"
    assert requests[0].url.params["settlementDateTo"] == "2026-07-02"


def test_forecast_request_uses_documented_publication_filters() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[])

    client = ElexonClient(_settings(), httpx.MockTransport(handler))
    try:
        client.get_forecasts(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
    finally:
        client.close()

    assert requests[0].url.path.endswith("/datasets/WINDFOR/stream")
    assert requests[0].url.params["publishDateTimeFrom"] == "2026-01-01T00:00:00Z"
    assert requests[0].url.params["publishDateTimeTo"] == "2026-01-02T00:00:00Z"


def test_http_errors_are_reported() -> None:
    client = ElexonClient(
        _settings(),
        httpx.MockTransport(lambda _request: httpx.Response(404)),
    )
    try:
        with pytest.raises(ElexonAPIError, match="HTTP 404"):
            client.get_forecasts(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 2, tzinfo=timezone.utc),
            )
    finally:
        client.close()


def test_invalid_json_and_invalid_response_shape_are_reported() -> None:
    invalid_json = ElexonClient(
        _settings(),
        httpx.MockTransport(
            lambda _request: httpx.Response(200, content=b"{not json")
        ),
    )
    try:
        with pytest.raises(ElexonAPIError, match="invalid JSON"):
            invalid_json.get_forecasts(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 2, tzinfo=timezone.utc),
            )
    finally:
        invalid_json.close()

    invalid_shape = ElexonClient(
        _settings(),
        httpx.MockTransport(
            lambda _request: httpx.Response(200, content=json.dumps({"rows": []}))
        ),
    )
    try:
        with pytest.raises(ElexonAPIError, match="expected a JSON array"):
            invalid_shape.get_forecasts(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 2, tzinfo=timezone.utc),
            )
    finally:
        invalid_shape.close()


def test_transient_http_error_is_retried() -> None:
    request_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return httpx.Response(503)
        return httpx.Response(200, json=[])

    client = ElexonClient(
        _settings(elexon_retry_count=1),
        httpx.MockTransport(handler),
    )
    try:
        assert client.get_forecasts(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
        ) == []
    finally:
        client.close()
    assert request_count == 2


def test_timeout_is_reported() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("request timed out")

    client = ElexonClient(_settings(), httpx.MockTransport(handler))
    try:
        with pytest.raises(ElexonAPIError, match="request failed after 1 attempts"):
            client.get_forecasts(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 2, tzinfo=timezone.utc),
            )
    finally:
        client.close()


def test_oversized_response_is_rejected() -> None:
    client = ElexonClient(
        _settings(max_response_bytes=2),
        httpx.MockTransport(
            lambda _request: httpx.Response(200, content=b"[] ")
        ),
    )
    try:
        with pytest.raises(ElexonAPIError, match="size limit"):
            client.get_forecasts(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 2, tzinfo=timezone.utc),
            )
    finally:
        client.close()
