"""API key creation against real PostgreSQL. Run with: uv run pytest -m integration

Keys are written to a throwaway schema built from `supabase/migrations`. `api_keys.user_id`
references `auth.users`, so the test borrows an existing Supabase user and is skipped if
there is none.
"""

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg_pool import ConnectionPool

from tracehound.api.app import create_app
from tracehound.api.dependencies import get_current_user
from tracehound.auth import User
from tracehound.db import create_pool
from tracehound.helpers.api_key_helper import ApiKeyManagement, api_key_hash_secret

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"

load_dotenv()
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL is not set"),
]


@pytest.fixture
def user_id() -> UUID:
    with psycopg.connect(os.environ["DATABASE_URL"], prepare_threshold=None) as conn:
        row = conn.execute("SELECT id FROM auth.users LIMIT 1").fetchone()
    if row is None:
        pytest.skip("no Supabase user to own the test keys")
    return row[0]


@pytest.fixture
def schema() -> Iterator[str]:
    """Create a schema holding every migration, and drop it afterwards."""
    name = f"test_{uuid4().hex[:12]}"
    with psycopg.connect(os.environ["DATABASE_URL"], prepare_threshold=None) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(name)))
        for migration in sorted(MIGRATIONS.glob("*.sql")):
            conn.execute(migration.read_text())
    try:
        yield name
    finally:
        with psycopg.connect(os.environ["DATABASE_URL"], prepare_threshold=None) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))


@pytest.fixture
def pool(schema: str) -> Iterator[ConnectionPool]:
    """A pool whose connections only see the test schema."""
    with create_pool(os.environ["DATABASE_URL"], options=f"-c search_path={schema}") as test_pool:
        yield test_pool


@pytest.fixture
def client(pool: ConnectionPool, user_id: UUID) -> Iterator[TestClient]:
    app = create_app(pool_factory=lambda: pool)
    app.dependency_overrides[get_current_user] = lambda: User(user_id=user_id)
    with TestClient(app) as test_client:
        yield test_client


def test_key_is_persisted_as_hash(client: TestClient, pool: ConnectionPool, user_id: UUID) -> None:
    response = client.post("/v1/api-keys", json={"name": "Alertmanager"})
    assert response.status_code == 201
    body = response.json()
    with pool.connection() as conn:
        row = conn.execute("SELECT * FROM api_keys WHERE id = %s", (body["id"],)).fetchone()
    assert row is not None
    assert row["user_id"] == user_id
    assert row["name"] == "Alertmanager"
    assert row["hash"] == ApiKeyManagement(pool, api_key_hash_secret()).hash_key(body["key"])
    assert body["key"] not in row.values()
    assert (row["prefix"], row["suffix"]) == (body["prefix"], body["suffix"])
    assert row["last_used_at"] is None
    assert row["revoked_at"] is None
