from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.routes import get_elexon_client
from app.main import app
from app.services.elexon_client import ElexonAPIError


class FakeElexonClient:
    def get_actuals(self, _start: datetime, _end: datetime) -> list[dict[str, object]]:
        return [
            {
                "fuelType": "WIND",
                "startTime": "2026-01-01T00:00:00Z",
                "generation": 100,
            },
            {
                "fuelType": "CCGT",
                "startTime": "2026-01-01T00:00:00Z",
                "generation": 900,
            },
        ]

    def get_forecasts(
        self,
        _publish_from: datetime,
        _publish_to: datetime,
    ) -> list[dict[str, object]]:
        return [
            {
                "startTime": "2026-01-01T00:00:00Z",
                "publishTime": "2025-12-31T00:00:00Z",
                "generation": 90,
            },
            {
                "startTime": "2026-01-01T00:00:00Z",
                "publishTime": "2025-12-31T01:00:00Z",
                "generation": 95,
            },
        ]


def test_actual_endpoint_returns_only_wind_records() -> None:
    app.dependency_overrides[get_elexon_client] = lambda: FakeElexonClient()
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/actuals",
                params={
                    "start_time": "2026-01-01T00:00:00Z",
                    "end_time": "2026-01-02T00:00:00Z",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert len(response.json()["records"]) == 1
    assert response.json()["records"][0]["actualGeneration"] == 100


def test_forecast_versions_endpoint_returns_all_versions_in_order() -> None:
    app.dependency_overrides[get_elexon_client] = lambda: FakeElexonClient()
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/forecast-versions",
                params={
                    "start_time": "2026-01-01T00:00:00Z",
                    "publish_from": "2025-12-30T00:00:00Z",
                    "publish_to": "2026-01-01T00:00:00Z",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [
        item["forecastGeneration"] for item in response.json()["records"]
    ] == [90, 95]


def test_accuracy_endpoint_selects_only_pre_cutoff_forecast() -> None:
    app.dependency_overrides[get_elexon_client] = lambda: FakeElexonClient()
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/forecast-accuracy",
                params={
                    "start_time": "2026-01-01T00:00:00Z",
                    "end_time": "2026-01-02T00:00:00Z",
                    "publish_from": "2025-12-30T00:00:00Z",
                    "publish_to": "2026-01-01T00:00:00Z",
                    "decision_lead_hours": 24,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["matched_observations"] == 1
    assert response.json()["mae"] == 10
    assert response.json()["bias"] == -10
    assert response.json()["actual_records"][0]["actualGeneration"] == 100
    assert response.json()["selected_forecasts"][0]["forecastGeneration"] == 90


def test_invalid_query_parameters_return_422() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/actuals",
            params={
                "start_time": "2026-01-01T00:00:00",
                "end_time": "2026-01-02T00:00:00Z",
            },
        )
    assert response.status_code == 422


def test_upstream_errors_are_reported_as_bad_gateway() -> None:
    class FailedClient:
        def get_actuals(self, _start: datetime, _end: datetime) -> list[dict[str, object]]:
            raise ElexonAPIError("Elexon API returned HTTP 503 after retries")

    app.dependency_overrides[get_elexon_client] = lambda: FailedClient()
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/actuals",
                params={
                    "start_time": "2026-01-01T00:00:00Z",
                    "end_time": "2026-01-02T00:00:00Z",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert response.json()["error"] == "elexon_api_error"
