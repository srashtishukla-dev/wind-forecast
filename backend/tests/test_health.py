from fastapi.testclient import TestClient

from app.main import app


def test_health_and_openapi_are_available() -> None:
    with TestClient(app) as client:
        health = client.get("/health")
        openapi = client.get("/openapi.json")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert openapi.status_code == 200
    assert "/api/forecast-accuracy" in openapi.json()["paths"]
