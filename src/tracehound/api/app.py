"""FastAPI application factory.

Run with: uvicorn tracehound.api.app:create_app --factory
"""

import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg_pool import ConnectionPool

from tracehound.api.incidents import router as incidents_router
from tracehound.db import create_pool, database_url
from tracehound.helpers.incident_helper import IncidentHelper


def _default_pool() -> ConnectionPool:
    load_dotenv()
    return create_pool(database_url())


def cors_origins() -> list[str]:
    """Browser origins allowed to call the API, from comma-separated `CORS_ORIGINS`."""
    raw = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def create_app(pool_factory: Callable[[], ConnectionPool] = _default_pool) -> FastAPI:
    """Build the app. The pool opens on startup and closes on shutdown.

    By default it connects to `DATABASE_URL`, read from the environment or `.env`.
    The UI calls the API from another origin, so CORS allows `CORS_ORIGINS`.
    """
    load_dotenv()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        with pool_factory() as pool:
            app.state.incident_helper = IncidentHelper(pool)
            yield

    app = FastAPI(title="Tracehound", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(incidents_router)
    return app
