"""Environment-backed application settings."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _read_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _read_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    elexon_api_base_url: str = "https://data.elexon.co.uk/bmrs/api/v1"
    elexon_request_timeout_seconds: float = 10.0
    elexon_retry_count: int = 2
    max_response_bytes: int = 20_000_000
    max_query_range_days: int = 31
    decision_lead_hours: float = 24.0
    cors_origins: tuple[str, ...] = ("http://localhost:3000", "http://localhost:5173")

    @classmethod
    def from_env(cls) -> Settings:
        """Create settings from process environment variables."""
        origins = os.getenv(
            "CORS_ORIGINS",
            "http://localhost:3000,http://localhost:5173",
        )
        return cls(
            elexon_api_base_url=os.getenv(
                "ELEXON_API_BASE_URL",
                "https://data.elexon.co.uk/bmrs/api/v1",
            ).rstrip("/"),
            elexon_request_timeout_seconds=_read_float(
                "ELEXON_REQUEST_TIMEOUT_SECONDS",
                10.0,
            ),
            elexon_retry_count=_read_int("ELEXON_RETRY_COUNT", 2),
            max_response_bytes=_read_int("MAX_RESPONSE_BYTES", 20_000_000),
            max_query_range_days=_read_int("MAX_QUERY_RANGE_DAYS", 31),
            decision_lead_hours=_read_float("DECISION_LEAD_HOURS", 24.0),
            cors_origins=tuple(origin.strip() for origin in origins.split(",") if origin.strip()),
        ).validated()

    def validated(self) -> Settings:
        """Reject unsafe or nonsensical resource and policy limits."""
        if (
            not math.isfinite(self.elexon_request_timeout_seconds)
            or self.elexon_request_timeout_seconds <= 0
        ):
            raise ValueError("ELEXON_REQUEST_TIMEOUT_SECONDS must be greater than zero")
        if not 0 <= self.elexon_retry_count <= 5:
            raise ValueError("ELEXON_RETRY_COUNT must be between 0 and 5")
        if self.max_response_bytes <= 0:
            raise ValueError("MAX_RESPONSE_BYTES must be greater than zero")
        if self.max_query_range_days <= 0:
            raise ValueError("MAX_QUERY_RANGE_DAYS must be greater than zero")
        if (
            not math.isfinite(self.decision_lead_hours)
            or not 0 <= self.decision_lead_hours <= 720
        ):
            raise ValueError("DECISION_LEAD_HOURS must be between 0 and 720")
        if not self.elexon_api_base_url.startswith(("https://", "http://")):
            raise ValueError("ELEXON_API_BASE_URL must be an HTTP(S) URL")
        return self
