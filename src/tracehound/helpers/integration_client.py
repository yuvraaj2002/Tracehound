"""Turn a stored integration into an authenticated HTTP client, and check that it works.

`IntegrationManagement.connection(s)` loads and decrypts the credential; this module never touches
the database. A `Connection` holds the plaintext secret, so it is kept out of reprs and logs.
"""

import ipaddress
import socket
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx

from tracehound.schemas.integration import IntegrationKind, allow_insecure_urls
from tracehound.tools.deploys.adapters.github import GitHubDeploySource
from tracehound.tools.logs.adapters.loki import LokiLogSource
from tracehound.tools.metrics.adapters.prometheus import PrometheusMetricSource
from tracehound.tools.traces.adapters.tempo import TempoTraceSource

DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
GITHUB_HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


@dataclass(frozen=True)
class Connection:
    """A stored integration with its decrypted credential, ready to build a client from."""

    id: Any
    kind: IntegrationKind
    config: dict[str, Any]
    secret: str | None = field(default=None, repr=False)


class UnsafeDestination(httpx.TransportError):
    """The URL's host resolves to a loopback, private or link-local address."""


def _check_destination(request: httpx.Request) -> None:
    """Refuse hosts that resolve to non-public addresses, unless insecure URLs are allowed.

    `check_backend_url` only sees the hostname when the integration is saved; this runs on every
    request, so a DNS name later pointed at an internal address is caught too.
    """
    if allow_insecure_urls():
        return
    host = request.url.host
    try:
        infos = socket.getaddrinfo(host, request.url.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise httpx.ConnectError(f"could not resolve {host}", request=request) from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise UnsafeDestination(f"{host} resolves to a private address", request=request)


def build_client(connection: Connection, timeout: httpx.Timeout = DEFAULT_TIMEOUT) -> httpx.Client:
    """An `httpx.Client` with the integration's base URL, credential and tenant header."""
    config = connection.config
    headers: dict[str, str] = {}
    auth: httpx.Auth | None = None
    match config.get("auth_type"):
        case "basic":
            auth = httpx.BasicAuth(config["username"], connection.secret or "")
        case "bearer":
            headers["Authorization"] = f"Bearer {connection.secret or ''}"
    if connection.kind == "github":
        headers.update(GITHUB_HEADERS)
    elif config.get("org_id"):
        headers["X-Scope-OrgID"] = config["org_id"]
    return httpx.Client(
        base_url=config["url"],
        auth=auth,
        headers=headers,
        timeout=timeout,
        follow_redirects=False,  # a redirect could carry the credential to another host
        event_hooks={"request": [_check_destination]},
    )


def _probe(connection: Connection) -> tuple[str, dict[str, str]]:
    """The cheapest authenticated read that the specialist's own queries also depend on."""
    match connection.kind:
        case "loki":
            return "/loki/api/v1/labels", {}
        case "prometheus":
            return "/api/v1/query", {"query": "1"}
        case "tempo":
            return "/api/search", {"limit": "1"}
        case "github":
            repository = connection.config.get("repository")
            if not repository:
                raise ValueError("no repository is set")
            return f"/repos/{repository}/deployments", {"per_page": "1"}
    raise ValueError(f"unknown integration kind {connection.kind!r}")


def _http_error(connection: Connection, code: int) -> str:
    if code in (401, 403):
        return f"credentials were rejected (HTTP {code})"
    if code == 404:
        if connection.kind == "github":
            return "repository not found, or the token can't read its deployments (HTTP 404)"
        return "endpoint not found, check the URL (HTTP 404)"
    return f"unexpected response (HTTP {code})"


def test_connection(connection: Connection, client: httpx.Client | None = None) -> str | None:
    """Make one authenticated read. Returns None on success, else a reason safe to show the user.

    The reason never includes the credential or the response body.
    """
    try:
        path, params = _probe(connection)
    except ValueError as exc:
        return str(exc)
    owned = client is None
    client = client or build_client(connection)
    try:
        response = client.get(path, params=params)
    except UnsafeDestination as exc:
        return str(exc)
    except httpx.TimeoutException:
        return "timed out"
    except httpx.TransportError:
        return f"could not connect to {httpx.URL(connection.config['url']).host}"
    finally:
        if owned:
            client.close()
    if response.is_success:
        return None
    return _http_error(connection, response.status_code)


test_connection.__test__ = False  # type: ignore[attr-defined]  # not a pytest test


@dataclass
class LiveSources:
    """The specialists' sources for one user's integrations. Close it to release the clients."""

    logs: LokiLogSource | None = None
    metrics: PrometheusMetricSource | None = None
    traces: TempoTraceSource | None = None
    deploys: GitHubDeploySource | None = None
    clients: list[httpx.Client] = field(default_factory=list, repr=False)

    def close(self) -> None:
        for client in self.clients:
            client.close()

    def __enter__(self) -> "LiveSources":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def live_sources(
    connections: Mapping[IntegrationKind, Connection], services: Iterable[str]
) -> LiveSources:
    """Build a source for each connected backend.

    GitHub integrations name one repository, so every service in `services` is read from it;
    deployments are told apart by the ``service`` key in their payload.
    """
    sources = LiveSources()

    def client_for(kind: IntegrationKind) -> httpx.Client:
        client = build_client(connections[kind])
        sources.clients.append(client)
        return client

    if "loki" in connections:
        label = connections["loki"].config.get("service_label", "service_name")
        sources.logs = LokiLogSource(client_for("loki"), service_label=label)
    if "prometheus" in connections:
        label = connections["prometheus"].config.get("service_label", "job")
        sources.metrics = PrometheusMetricSource(client_for("prometheus"), service_label=label)
    if "tempo" in connections:
        sources.traces = TempoTraceSource(client_for("tempo"))
    if "github" in connections:
        repository = connections["github"].config.get("repository")
        if repository:
            repos = dict.fromkeys(services, repository)
            sources.deploys = GitHubDeploySource(client_for("github"), repos=repos)
    return sources
