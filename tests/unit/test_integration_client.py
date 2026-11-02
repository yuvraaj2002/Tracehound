import base64
import socket
from uuid import uuid4

import httpx
import pytest

from tracehound.helpers import integration_client
from tracehound.helpers.integration_client import (
    Connection,
    UnsafeDestination,
    build_client,
    live_sources,
    test_connection,
)


def _connection(kind="loki", secret="s3cret", **config) -> Connection:
    defaults = {"url": "https://backend.example.com", "auth_type": "basic", "username": "123"}
    return Connection(id=uuid4(), kind=kind, config={**defaults, **config}, secret=secret)


def _client(connection: Connection, handler) -> httpx.Client:
    """`build_client`'s settings over a mock transport, so nothing leaves the process."""
    real = build_client(connection)
    return httpx.Client(
        base_url=real.base_url,
        auth=real.auth,
        headers=real.headers,
        transport=httpx.MockTransport(handler),
    )


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch):
    monkeypatch.delenv("ALLOW_INSECURE_INTEGRATION_URLS", raising=False)
    monkeypatch.setattr(
        integration_client.socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )


def test_basic_auth_and_tenant_header_are_sent():
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, json={"status": "success", "data": []})

    connection = _connection(org_id="tenant-1")
    assert test_connection(connection, _client(connection, handler)) is None
    assert seen["authorization"] == "Basic " + base64.b64encode(b"123:s3cret").decode()
    assert seen["x-scope-orgid"] == "tenant-1"


def test_github_uses_bearer_token_and_reads_the_repository_deployments():
    seen = {}

    def handler(request):
        seen["auth"], seen["path"] = request.headers["authorization"], request.url.path
        return httpx.Response(200, json=[])

    connection = _connection(
        "github",
        "github_pat_x",
        url="https://api.github.com",
        auth_type="bearer",
        repository="acme/checkout",
    )
    assert test_connection(connection, _client(connection, handler)) is None
    assert seen == {"auth": "Bearer github_pat_x", "path": "/repos/acme/checkout/deployments"}


@pytest.mark.parametrize(
    ("code", "reason"),
    [(401, "credentials were rejected (HTTP 401)"), (404, "endpoint not found, check the URL")],
)
def test_failures_give_a_reason_without_the_secret(code, reason):
    connection = _connection()
    error = test_connection(connection, _client(connection, lambda r: httpx.Response(code)))
    assert error is not None and error.startswith(reason)
    assert "s3cret" not in error


def test_github_without_a_repository_fails_before_any_request():
    connection = _connection("github", auth_type="bearer", repository=None)
    assert test_connection(connection) == "no repository is set"


def test_private_destinations_are_refused(monkeypatch):
    monkeypatch.setattr(
        integration_client.socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443))],
    )
    with pytest.raises(UnsafeDestination):
        build_client(_connection()).get("/loki/api/v1/labels")


def test_secret_is_not_in_the_repr():
    assert "s3cret" not in repr(_connection())


def test_live_sources_builds_one_source_per_connected_backend():
    connections = {
        "loki": _connection("loki"),
        "github": _connection("github", auth_type="bearer", repository="acme/checkout"),
    }
    with live_sources(connections, ["checkout-api"]) as sources:
        assert sources.logs is not None and sources.deploys is not None
        assert sources.metrics is None and sources.traces is None
        assert len(sources.clients) == 2
    assert all(client.is_closed for client in sources.clients)
