import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import psycopg
import pytest
from cryptography.exceptions import InvalidTag
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.unit.test_api_keys import USER_ID, VERIFIER, _auth
from tracehound.api.app import create_app
from tracehound.api.dependencies import get_integration_management, get_token_verifier
from tracehound.helpers.integration_helper import (
    IntegrationExists,
    IntegrationManagement,
    SecretBox,
    integration_encryption_key,
)
from tracehound.schemas import IntegrationCreateRequest, IntegrationList, IntegrationSummary

GRAFANA_CLOUD = {
    "kind": "loki",
    "config": {"url": "https://logs-prod-012.grafana.net/", "service_label": "service_name"},
    "auth": {"type": "basic", "username": "123456", "password": "glc_secret"},
}


class MemoryIntegrations:
    """In-memory stand-in for `IntegrationManagement`, so these tests need no database."""

    def __init__(self) -> None:
        self.created: list[tuple[UUID, IntegrationCreateRequest]] = []
        self.summaries: list[tuple[UUID, IntegrationSummary]] = []

    def create(self, user_id: UUID, request: IntegrationCreateRequest) -> IntegrationSummary:
        if any(uid == user_id and r.kind == request.kind for uid, r in self.created):
            raise IntegrationExists(request.kind)
        self.created.append((user_id, request))
        config, secret = IntegrationManagement.split_auth(request)
        summary = IntegrationSummary(
            id=uuid4(),
            kind=request.kind,
            config=config,
            has_secret=secret is not None,
            status="untested",
            created_at=datetime.now(UTC),
        )
        self.summaries.append((user_id, summary))
        return summary

    def list(self, user_id: UUID) -> IntegrationList:
        return IntegrationList(items=[s for uid, s in self.summaries if uid == user_id])

    def delete(self, user_id: UUID, integration_id: UUID) -> bool:
        for i, (uid, summary) in enumerate(self.summaries):
            if uid == user_id and summary.id == integration_id:
                del self.summaries[i]
                self.created = [
                    (u, r) for u, r in self.created if (u, r.kind) != (uid, summary.kind)
                ]
                return True
        return False


class BrokenIntegrations:
    def create(self, user_id: UUID, request: IntegrationCreateRequest) -> IntegrationSummary:
        raise psycopg.OperationalError("connection lost")

    def list(self, user_id: UUID) -> IntegrationList:
        raise psycopg.OperationalError("connection lost")

    def delete(self, user_id: UUID, integration_id: UUID) -> bool:
        raise psycopg.OperationalError("connection lost")


def _app_with(integrations: object) -> FastAPI:
    app = create_app(pool_factory=lambda: pytest.fail("pool should not open"))
    app.dependency_overrides[get_integration_management] = lambda: integrations
    app.dependency_overrides[get_token_verifier] = lambda: VERIFIER
    return app


@pytest.fixture
def integrations() -> MemoryIntegrations:
    return MemoryIntegrations()


@pytest.fixture
def client(integrations: MemoryIntegrations) -> TestClient:
    return TestClient(_app_with(integrations))


def _with(**changes: object) -> dict:
    return {**GRAFANA_CLOUD, **changes}


# Encryption


def test_secret_box_round_trip() -> None:
    box = SecretBox(os.urandom(32))
    sealed = box.encrypt("glc_secret", b"row-1")
    assert b"glc_secret" not in sealed
    assert box.decrypt(sealed, b"row-1") == "glc_secret"
    assert box.encrypt("glc_secret", b"row-1") != sealed  # fresh nonce each time


def test_secret_box_rejects_other_row_or_key() -> None:
    box = SecretBox(os.urandom(32))
    sealed = box.encrypt("glc_secret", b"row-1")
    with pytest.raises(InvalidTag):
        box.decrypt(sealed, b"row-2")
    with pytest.raises(InvalidTag):
        SecretBox(os.urandom(32)).decrypt(sealed, b"row-1")


@pytest.mark.parametrize("value", [None, "not base64!", "c2hvcnQ="])
def test_encryption_key_must_be_32_bytes(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("INTEGRATION_ENCRYPTION_KEY", raising=False)
    else:
        monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", value)
    with pytest.raises(RuntimeError):
        integration_encryption_key()


# POST /v1/integrations


def test_creates_loki_integration(client: TestClient, integrations: MemoryIntegrations) -> None:
    response = client.post("/v1/integrations", json=GRAFANA_CLOUD, headers=_auth())
    assert response.status_code == 201
    body = response.json()
    assert body["config"] == {
        "url": "https://logs-prod-012.grafana.net",
        "service_label": "service_name",
        "org_id": None,
        "auth_type": "basic",
        "username": "123456",
    }
    assert body["has_secret"] is True
    assert body["status"] == "untested"
    assert "glc_secret" not in response.text
    assert integrations.created[0][0] == USER_ID


def test_no_auth_has_no_secret(client: TestClient) -> None:
    payload = _with(
        config={"url": "https://loki.acme.com", "org_id": "acme-prod"}, auth={"type": "none"}
    )
    response = client.post("/v1/integrations", json=payload, headers=_auth())
    assert response.status_code == 201
    assert response.json()["has_secret"] is False
    assert response.json()["config"]["org_id"] == "acme-prod"


def test_bearer_token_is_not_returned(client: TestClient) -> None:
    payload = _with(auth={"type": "bearer", "token": "eyJ-secret"})
    response = client.post("/v1/integrations", json=payload, headers=_auth())
    assert response.status_code == 201
    assert response.json()["config"]["auth_type"] == "bearer"
    assert "eyJ-secret" not in response.text


def test_second_loki_integration_conflicts(client: TestClient) -> None:
    assert client.post("/v1/integrations", json=GRAFANA_CLOUD, headers=_auth()).status_code == 201
    response = client.post("/v1/integrations", json=GRAFANA_CLOUD, headers=_auth())
    assert response.status_code == 409


def test_requires_valid_token(client: TestClient, integrations: MemoryIntegrations) -> None:
    response = client.post("/v1/integrations", json=GRAFANA_CLOUD)
    assert response.status_code == 401
    assert integrations.created == []


@pytest.mark.parametrize(
    "url",
    [
        "http://logs.example.com",
        "https://localhost:3100",
        "https://127.0.0.1",
        "https://10.0.0.5",
        "https://169.254.169.254",
        "https://[::1]",
        "https://user:pw@logs.example.com",
        "https://logs.example.com?x=1",
        "ftp://logs.example.com",
        "logs.example.com",
    ],
)
def test_rejects_unsafe_url(client: TestClient, url: str) -> None:
    payload = _with(config={"url": url})
    assert client.post("/v1/integrations", json=payload, headers=_auth()).status_code == 422


def test_insecure_urls_allowed_in_local_dev(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALLOW_INSECURE_INTEGRATION_URLS", "1")
    payload = _with(config={"url": "http://localhost:3100"}, auth={"type": "none"})
    assert client.post("/v1/integrations", json=payload, headers=_auth()).status_code == 201


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "prometheus"},
        {"auth": {"type": "basic", "username": "123456"}},
        {"auth": {"type": "none", "token": "leftover"}},
        {"auth": {"type": "oauth"}},
        {"config": {"url": "https://loki.acme.com", "service_label": "bad-label"}},
        {"config": {"url": "https://loki.acme.com", "password": "misplaced"}},
        {"user_id": str(uuid4())},
    ],
)
def test_rejects_invalid_payload(client: TestClient, changes: dict) -> None:
    payload = _with(**changes)
    assert client.post("/v1/integrations", json=payload, headers=_auth()).status_code == 422


def test_validation_error_does_not_echo_secret(client: TestClient) -> None:
    payload = _with(config={"url": "http://bad"})
    response = client.post("/v1/integrations", json=payload, headers=_auth())
    assert response.status_code == 422
    assert "glc_secret" not in response.text


def test_database_error_returns_500() -> None:
    client = TestClient(_app_with(BrokenIntegrations()))
    response = client.post("/v1/integrations", json=GRAFANA_CLOUD, headers=_auth())
    assert response.status_code == 500
    assert response.json() == {"detail": "Could not save the integration."}


# GET /v1/integrations


def test_lists_only_own_integrations(client: TestClient, integrations: MemoryIntegrations) -> None:
    assert client.get("/v1/integrations", headers=_auth()).json() == {"items": []}
    integrations.create(uuid4(), IntegrationCreateRequest.model_validate(GRAFANA_CLOUD))
    created = client.post("/v1/integrations", json=GRAFANA_CLOUD, headers=_auth()).json()
    response = client.get("/v1/integrations", headers=_auth())
    assert response.status_code == 200
    assert response.json() == {"items": [created]}
    assert "glc_secret" not in response.text


def test_list_requires_valid_token(client: TestClient) -> None:
    assert client.get("/v1/integrations").status_code == 401


def test_list_database_error_returns_500() -> None:
    client = TestClient(_app_with(BrokenIntegrations()))
    response = client.get("/v1/integrations", headers=_auth())
    assert response.status_code == 500
    assert response.json() == {"detail": "Could not list the integrations."}


# DELETE /v1/integrations/{id}


def test_deletes_integration(client: TestClient) -> None:
    created = client.post("/v1/integrations", json=GRAFANA_CLOUD, headers=_auth()).json()
    response = client.delete(f"/v1/integrations/{created['id']}", headers=_auth())
    assert response.status_code == 204
    assert response.content == b""
    assert client.get("/v1/integrations", headers=_auth()).json() == {"items": []}
    # The kind is free again.
    assert client.post("/v1/integrations", json=GRAFANA_CLOUD, headers=_auth()).status_code == 201


def test_cannot_delete_other_users_integration(
    client: TestClient, integrations: MemoryIntegrations
) -> None:
    other = uuid4()
    theirs = integrations.create(other, IntegrationCreateRequest.model_validate(GRAFANA_CLOUD))
    response = client.delete(f"/v1/integrations/{theirs.id}", headers=_auth())
    assert response.status_code == 404
    assert integrations.list(other).items == [theirs]


def test_delete_unknown_integration_returns_404(client: TestClient) -> None:
    response = client.delete(f"/v1/integrations/{uuid4()}", headers=_auth())
    assert response.status_code == 404
    assert response.json() == {"detail": "Integration not found."}


def test_delete_rejects_malformed_id(client: TestClient) -> None:
    assert client.delete("/v1/integrations/not-a-uuid", headers=_auth()).status_code == 422


def test_delete_requires_valid_token(client: TestClient) -> None:
    assert client.delete(f"/v1/integrations/{uuid4()}").status_code == 401


def test_delete_database_error_returns_500() -> None:
    client = TestClient(_app_with(BrokenIntegrations()))
    response = client.delete(f"/v1/integrations/{uuid4()}", headers=_auth())
    assert response.status_code == 500
    assert response.json() == {"detail": "Could not delete the integration."}
