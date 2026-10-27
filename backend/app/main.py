"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import Settings
from app.services.data_processing import DataProcessingError
from app.services.elexon_client import ElexonAPIError, ElexonClient


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application and initialize its Elexon client on startup."""
    app_settings = (settings or Settings.from_env()).validated()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        client = ElexonClient(app_settings)
        application.state.settings = app_settings
        application.state.elexon_client = client
        try:
            yield
        finally:
            client.close()

    application = FastAPI(
        title="UK Wind Forecast Analytics API",
        description=(
            "Historical Elexon wind generation and forecast accuracy. "
            "All API time filters use timezone-aware timestamps."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    application.include_router(router)

    @application.exception_handler(ElexonAPIError)
    async def handle_elexon_error(
        _request: Request,
        exc: ElexonAPIError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={"detail": str(exc), "error": "elexon_api_error"},
        )

    @application.exception_handler(DataProcessingError)
    async def handle_source_data_error(
        _request: Request,
        exc: DataProcessingError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={"detail": str(exc), "error": "elexon_data_error"},
        )

    return application


app = create_app()
