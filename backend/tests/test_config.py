from app.config import Settings


def test_settings_are_read_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("ELEXON_API_BASE_URL", "https://api.example/bmrs/api/v1/")
    monkeypatch.setenv("ELEXON_REQUEST_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("ELEXON_RETRY_COUNT", "1")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:4000,https://ui.example")
    monkeypatch.setenv("DECISION_LEAD_HOURS", "18")

    settings = Settings.from_env()

    assert settings.elexon_api_base_url == "https://api.example/bmrs/api/v1"
    assert settings.elexon_request_timeout_seconds == 3.5
    assert settings.elexon_retry_count == 1
    assert settings.cors_origins == (
        "http://localhost:4000",
        "https://ui.example",
    )
    assert settings.decision_lead_hours == 18
