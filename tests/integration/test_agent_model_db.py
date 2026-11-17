"""Per-agent model choices against real PostgreSQL. Run with: uv run pytest -m integration

Rows are written to a throwaway schema built from `supabase/migrations`, owned by a borrowed
Supabase user (see `test_api_key_db`).
"""

from uuid import UUID

import psycopg.errors
import pytest
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from tests.integration.test_api_key_db import client, engine, pool, pytestmark, schema, user_id
from tracehound.helpers.agent_model_helper import default_choice

__all__ = ["client", "engine", "pool", "pytestmark", "schema", "user_id"]

GEMMA = "google/gemma-4-26b-a4b-it:free"
LOGS = {"provider": "google", "model": GEMMA}
METRICS = {"provider": "cohere", "model": "cohere/north-mini-code:free"}


def test_choices_are_stored_per_agent_in_one_row(
    client: TestClient, pool: ConnectionPool, user_id: UUID
) -> None:
    fresh = client.get("/v1/agent-models/preferences").json()
    assert (fresh["customized"], fresh["configured"]) == ([], False)

    first = client.put("/v1/agent-models/preferences/logs", json=LOGS)
    assert first.status_code == 200
    assert first.json()["agents"]["logs"] == LOGS
    assert first.json()["configured"] is True

    second = client.put("/v1/agent-models/preferences/metrics", json=METRICS)
    body = second.json()
    assert body["agents"]["logs"] == LOGS, "saving metrics must not erase logs"
    assert body["agents"]["metrics"] == METRICS
    assert sorted(body["customized"]) == ["logs", "metrics"]
    assert body["agents"]["triage"] == default_choice("triage").model_dump()

    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_model_settings WHERE user_id = %s", (user_id,)
        ).fetchall()
    assert len(rows) == 1
    assert set(rows[0]["config"]["agents"]) == {"logs", "metrics"}
    assert rows[0]["updated_at"] >= rows[0]["created_at"]


def test_changing_an_agent_replaces_its_choice(client: TestClient) -> None:
    client.put("/v1/agent-models/preferences/logs", json=LOGS)
    changed = {"provider": "nvidia", "model": "nvidia/nemotron-3.5-lightning:free"}
    body = client.put("/v1/agent-models/preferences/logs", json=changed).json()
    assert body["agents"]["logs"] == changed
    assert body["customized"] == ["logs"]


def test_an_invalid_choice_is_not_stored(
    client: TestClient, pool: ConnectionPool, user_id: UUID
) -> None:
    bad = client.put("/v1/agent-models/preferences/logs", json={**LOGS, "model": "x/y"})
    assert bad.status_code == 422
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT 1 FROM agent_model_settings WHERE user_id = %s", (user_id,)
        ).fetchall()
    assert rows == []


def test_config_must_be_a_json_object(pool: ConnectionPool, user_id: UUID) -> None:
    with pool.connection() as conn, pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO agent_model_settings (user_id, config) VALUES (%s, '[]')", (user_id,)
        )
