"""Integration storage against real PostgreSQL. Run with: uv run pytest -m integration

Rows are written to a throwaway schema built from `supabase/migrations`, owned by a borrowed
Supabase user (see `test_api_key_db`).
"""

from uuid import UUID

from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from tests.integration.test_api_key_db import client, pool, pytestmark, schema, user_id
from tracehound.helpers.integration_helper import SecretBox, integration_encryption_key

__all__ = ["client", "pool", "pytestmark", "schema", "user_id"]

GRAFANA_CLOUD = {
    "kind": "loki",
    "config": {"url": "https://logs-prod-012.grafana.net"},
    "auth": {"type": "basic", "username": "123456", "password": "glc_secret"},
}


def test_credential_is_stored_encrypted(
    client: TestClient, pool: ConnectionPool, user_id: UUID
) -> None:
    response = client.post("/v1/integrations", json=GRAFANA_CLOUD)
    assert response.status_code == 201
    body = response.json()
    with pool.connection() as conn:
        row = conn.execute("SELECT * FROM integrations WHERE id = %s", (body["id"],)).fetchone()
    assert row is not None
    assert row["user_id"] == user_id
    assert row["kind"] == "loki"
    assert row["config"] == body["config"]
    assert "glc_secret" not in str(row["config"])
    assert b"glc_secret" not in row["secret_ciphertext"]
    assert row["secret_key_version"] == 1
    box = SecretBox(integration_encryption_key())
    assert box.decrypt(row["secret_ciphertext"], UUID(body["id"]).bytes) == "glc_secret"
    assert row["status"] == "untested"


def test_no_auth_stores_no_secret(client: TestClient, pool: ConnectionPool) -> None:
    payload = {**GRAFANA_CLOUD, "auth": {"type": "none"}}
    body = client.post("/v1/integrations", json=payload).json()
    with pool.connection() as conn:
        row = conn.execute("SELECT * FROM integrations WHERE id = %s", (body["id"],)).fetchone()
    assert row is not None
    assert (row["secret_ciphertext"], row["secret_key_version"]) == (None, None)


def test_second_loki_integration_conflicts(client: TestClient) -> None:
    assert client.post("/v1/integrations", json=GRAFANA_CLOUD).status_code == 201
    assert client.post("/v1/integrations", json=GRAFANA_CLOUD).status_code == 409


def test_lists_stored_integrations(client: TestClient) -> None:
    assert client.get("/v1/integrations").json() == {"items": []}
    created = client.post("/v1/integrations", json=GRAFANA_CLOUD).json()
    response = client.get("/v1/integrations")
    assert response.status_code == 200
    assert response.json() == {"items": [created]}
    assert "glc_secret" not in response.text


def test_delete_removes_row_and_frees_kind(client: TestClient, pool: ConnectionPool) -> None:
    created = client.post("/v1/integrations", json=GRAFANA_CLOUD).json()
    assert client.delete(f"/v1/integrations/{created['id']}").status_code == 204
    with pool.connection() as conn:
        row = conn.execute("SELECT 1 FROM integrations WHERE id = %s", (created["id"],)).fetchone()
    assert row is None
    assert client.delete(f"/v1/integrations/{created['id']}").status_code == 404
    assert client.post("/v1/integrations", json=GRAFANA_CLOUD).status_code == 201


def test_update_keeps_or_replaces_secret(client: TestClient, pool: ConnectionPool) -> None:
    created = client.post("/v1/integrations", json=GRAFANA_CLOUD).json()
    integration_id = UUID(created["id"])
    with pool.connection() as conn:
        conn.execute(
            "UPDATE integrations SET status = 'active', last_tested_at = now(),"
            " last_error = 'old' WHERE id = %s",
            (integration_id,),
        )
        before = conn.execute(
            "SELECT * FROM integrations WHERE id = %s", (integration_id,)
        ).fetchone()
    assert before is not None

    patched = client.patch(
        f"/v1/integrations/{integration_id}",
        json={"config": {"url": "https://logs-prod-020.grafana.net"}},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "untested"
    with pool.connection() as conn:
        row = conn.execute("SELECT * FROM integrations WHERE id = %s", (integration_id,)).fetchone()
    assert row is not None
    assert row["config"]["url"] == "https://logs-prod-020.grafana.net"
    assert row["config"]["username"] == "123456"
    assert row["secret_ciphertext"] == before["secret_ciphertext"]
    assert (row["status"], row["last_tested_at"], row["last_error"]) == ("untested", None, None)
    assert row["updated_at"] > before["updated_at"]

    new_auth = {"type": "basic", "username": "654321", "password": "glc_rotated"}
    assert (
        client.patch(f"/v1/integrations/{integration_id}", json={"auth": new_auth}).status_code
        == 200
    )
    with pool.connection() as conn:
        row = conn.execute("SELECT * FROM integrations WHERE id = %s", (integration_id,)).fetchone()
    assert row is not None
    assert row["config"]["username"] == "654321"
    box = SecretBox(integration_encryption_key())
    assert box.decrypt(row["secret_ciphertext"], integration_id.bytes) == "glc_rotated"

    none_auth = {"auth": {"type": "none"}}
    assert client.patch(f"/v1/integrations/{integration_id}", json=none_auth).status_code == 200
    with pool.connection() as conn:
        row = conn.execute("SELECT * FROM integrations WHERE id = %s", (integration_id,)).fetchone()
    assert row is not None
    assert (row["secret_ciphertext"], row["secret_key_version"]) == (None, None)
    assert "username" not in row["config"]
