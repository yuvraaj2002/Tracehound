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
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from sqlalchemy import Engine

from tracehound.api.app import create_app
from tracehound.api.dependencies import get_current_user
from tracehound.auth import User
from tracehound.db import SessionFactory, create_db_engine, create_session_factory
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
    """A raw psycopg pool on the test schema, for checking rows independently of the ORM."""
    kwargs = {
        "row_factory": dict_row,
        "prepare_threshold": None,
        "options": f"-c search_path={schema}",
    }
    with ConnectionPool(
        os.environ["DATABASE_URL"], kwargs=kwargs, min_size=1, max_size=2
    ) as test_pool:
        yield test_pool


@pytest.fixture
def engine(schema: str) -> Iterator[Engine]:
    """The app's SQLAlchemy engine, pointed at the test schema."""
    test_engine = create_db_engine(os.environ["DATABASE_URL"], options=f"-c search_path={schema}")
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def sessions(engine: Engine) -> SessionFactory:
    return create_session_factory(engine)


@pytest.fixture
def client(engine: Engine, user_id: UUID) -> Iterator[TestClient]:
    app = create_app(engine_factory=lambda: engine)
    app.dependency_overrides[get_current_user] = lambda: User(user_id=user_id)
    with TestClient(app) as test_client:
        yield test_client


def test_key_is_persisted_as_hash(
    sessions: SessionFactory, client: TestClient, pool: ConnectionPool, user_id: UUID
) -> None:
    response = client.post("/v1/api-keys", json={"name": "Alertmanager"})
    assert response.status_code == 201
    body = response.json()
    with pool.connection() as conn:
        row = conn.execute("SELECT * FROM api_keys WHERE id = %s", (body["id"],)).fetchone()
    assert row is not None
    assert row["user_id"] == user_id
    assert row["name"] == "Alertmanager"
    assert row["hash"] == ApiKeyManagement(sessions, api_key_hash_secret()).hash_key(body["key"])
    assert body["key"] not in row.values()
    assert (row["prefix"], row["suffix"]) == (body["prefix"], body["suffix"])
    assert row["last_used_at"] is None
    assert row["revoked_at"] is None


def test_at_most_five_active_keys_per_user(client: TestClient) -> None:
    created = [client.post("/v1/api-keys", json={"name": f"key-{i}"}) for i in range(5)]
    assert [r.status_code for r in created] == [201] * 5
    assert client.post("/v1/api-keys", json={"name": "sixth"}).status_code == 409
    # Revoked keys don't count, so revoking one frees a slot.
    assert client.delete(f"/v1/api-keys/{created[0].json()['id']}").status_code == 204
    assert client.post("/v1/api-keys", json={"name": "sixth"}).status_code == 201


def test_rename_changes_only_the_name(client: TestClient, pool: ConnectionPool) -> None:
    created = client.post("/v1/api-keys", json={"name": "ci"}).json()
    response = client.put(f"/v1/api-keys/{created['id']}", json={"new_name": "deploy bot"})
    assert response.status_code == 200
    assert response.json()["name"] == "deploy bot"
    with pool.connection() as conn:
        row = conn.execute("SELECT * FROM api_keys WHERE id = %s", (created["id"],)).fetchone()
    assert row is not None
    assert row["name"] == "deploy bot"
    assert (row["prefix"], row["suffix"]) == (created["prefix"], created["suffix"])
    assert row["updated_at"] > row["created_at"]
    # A revoked key can't be renamed.
    assert client.delete(f"/v1/api-keys/{created['id']}").status_code == 204
    assert client.put(f"/v1/api-keys/{created['id']}", json={"new_name": "x"}).status_code == 404
