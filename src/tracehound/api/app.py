"""FastAPI application factory.

Run with: uvicorn tracehound.api.app:create_app --factory
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from psycopg_pool import ConnectionPool

from tracehound.api.incidents import router as incidents_router
from tracehound.db import create_pool, database_url
from tracehound.helpers.incident_helper import IncidentHelper


def _default_pool() -> ConnectionPool:
    load_dotenv()
    return create_pool(database_url())


def create_app(pool_factory: Callable[[], ConnectionPool] = _default_pool) -> FastAPI:
    """Build the app. The pool opens on startup and closes on shutdown.

    By default it connects to `DATABASE_URL`, read from the environment or `.env`.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        with pool_factory() as pool:
            app.state.incident_helper = IncidentHelper(pool)
            yield

    app = FastAPI(title="Tracehound", version="0.1.0", lifespan=lifespan)
    app.include_router(incidents_router)
    return app
