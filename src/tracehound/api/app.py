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

from tracehound.api.api_keys import router as api_keys_router
from tracehound.api.incidents import router as incidents_router
from tracehound.api.integrations import router as integrations_router
from tracehound.api.me import router as me_router
from tracehound.api.plans import router as plans_router
from tracehound.auth import TokenVerifier, supabase_url
from tracehound.db import create_pool, database_url
from tracehound.helpers.api_key_helper import api_key_hash_secret
from tracehound.helpers.incident_helper import IncidentHelper
from tracehound.helpers.integration_helper import integration_encryption_key


def _default_pool() -> ConnectionPool:
    load_dotenv()
    return create_pool(database_url())


def cors_origins() -> list[str]:
    """Browser origins allowed to call the API, from comma-separated `CORS_ORIGINS`."""
    raw = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def create_app(pool_factory: Callable[[], ConnectionPool] = _default_pool) -> FastAPI:
    """Build the app. The pool opens on startup and closes on shutdown.

    By default it connects to `DATABASE_URL`, read from the environment or `.env`. Startup also
    needs `SUPABASE_URL` (to verify access tokens), `API_KEY_HASH_SECRET` and
    `INTEGRATION_ENCRYPTION_KEY`.
    The UI calls the API from another origin, so CORS allows `CORS_ORIGINS`.
    """
    load_dotenv()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        with pool_factory() as pool:
            app.state.incident_helper = IncidentHelper(pool)
            app.state.pool = pool
            app.state.api_key_hash_secret = api_key_hash_secret()
            app.state.integration_encryption_key = integration_encryption_key()
            app.state.token_verifier = TokenVerifier.for_project(supabase_url())
            yield

    app = FastAPI(title="Tracehound", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(incidents_router)
    app.include_router(api_keys_router)
    app.include_router(integrations_router)
    app.include_router(plans_router)
    app.include_router(me_router)
    return app
