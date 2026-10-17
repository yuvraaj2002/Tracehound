"""FastAPI application factory.

Run with: uvicorn tracehound.api.app:create_app --factory
"""

import os
from pathlib import Path

from fastapi import FastAPI

from tracehound.api.incidents import router as incidents_router
from tracehound.store import IncidentStore

DEFAULT_DB_PATH = Path("data/tracehound.db")


def create_app(db_path: Path | None = None) -> FastAPI:
    path = db_path or Path(os.environ.get("TRACEHOUND_DB_PATH", DEFAULT_DB_PATH))
    app = FastAPI(title="Tracehound", version="0.1.0")
    app.state.incident_store = IncidentStore(path)
    app.include_router(incidents_router)
    return app
