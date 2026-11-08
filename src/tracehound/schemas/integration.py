"""Integration contracts: a user's connection to a telemetry backend."""

import ipaddress
import os
from typing import Annotated, Any, Literal, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

# Stored kinds, one per specialist.
IntegrationKind = Literal["loki", "prometheus", "tempo", "github"]
IntegrationStatus = Literal["untested", "active", "failing"]


def allow_insecure_urls() -> bool:
    """Whether `ALLOW_INSECURE_INTEGRATION_URLS=1` permits http and private hosts (local dev)."""
    return os.environ.get("ALLOW_INSECURE_INTEGRATION_URLS") == "1"


def check_backend_url(url: str) -> str:
    """Return `url` without a trailing slash, or raise `ValueError` if the server mustn't call it.

    The server fetches this URL, so outside local dev it must be https and must not name a
    loopback, private or link-local host (e.g. the cloud metadata address 169.254.169.254).
    Hostnames are resolved and checked again when a connection is made, which also covers
    DNS names that point at internal addresses.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("must be an http(s) URL with a host")
    if parts.query or parts.fragment or parts.username or parts.password:
        raise ValueError("must not contain a query, fragment or credentials")
    if not allow_insecure_urls():
        if parts.scheme != "https":
            raise ValueError("must use https")
        if parts.hostname == "localhost" or parts.hostname.endswith(".localhost"):
            raise ValueError("must not point at a private address")
        try:
            address = ipaddress.ip_address(parts.hostname)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError("must not point at a private address")
    return url.rstrip("/")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NoAuth(_Strict):
    type: Literal["none"]


class BasicAuth(_Strict):
    """Username and password, e.g. a Grafana Cloud user ID and access-policy token."""

    type: Literal["basic"]
    username: str = Field(min_length=1, max_length=200)
    password: SecretStr = Field(min_length=1, max_length=4096)


class BearerAuth(_Strict):
    type: Literal["bearer"]
    token: SecretStr = Field(min_length=1, max_length=4096)


IntegrationAuth = Annotated[NoAuth | BasicAuth | BearerAuth, Field(discriminator="type")]


SERVICE_LABEL_PATTERN = r"^[a-zA-Z_][a-zA-Z0-9_]*$"
REPOSITORY_PATTERN = r"^[\w.-]+/[\w.-]+$"


class TelemetryConfig(_Strict):
    """Non-secret backend settings. `org_id` is sent as `X-Scope-OrgID` when multi-tenant."""

    url: str = Field(max_length=2048)
    service_label: str = Field(
        default="service_name", min_length=1, max_length=100, pattern=SERVICE_LABEL_PATTERN
    )
    org_id: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("url")
    @classmethod
    def _check_url(cls, url: str) -> str:
        return check_backend_url(url)


class PrometheusConfig(TelemetryConfig):
    """Prometheus settings. Scrape targets name their service with `job`, not `service_name`."""

    service_label: str = Field(
        default="job", min_length=1, max_length=100, pattern=SERVICE_LABEL_PATTERN
    )


class GitHubConfig(_Strict):
    """GitHub settings: the API base URL and the `owner/name` repository to read deploys from."""

    url: str = Field(default="https://api.github.com", max_length=2048)
    repository: str = Field(min_length=3, max_length=200, pattern=REPOSITORY_PATTERN)

    @field_validator("url")
    @classmethod
    def _check_url(cls, url: str) -> str:
        return check_backend_url(url)


class _CreateRequest(_Strict):
    auth: IntegrationAuth


class LokiCreateRequest(_CreateRequest):
    kind: Literal["loki"]
    config: TelemetryConfig


class PrometheusCreateRequest(_CreateRequest):
    kind: Literal["prometheus"]
    config: PrometheusConfig


class TempoCreateRequest(_CreateRequest):
    kind: Literal["tempo"]
    config: TelemetryConfig


class GitHubCreateRequest(_CreateRequest):
    kind: Literal["github"]
    config: GitHubConfig


# Payload for ``POST /v1/integrations``. The credential in `auth` is stored encrypted.
IntegrationCreateRequest = Annotated[
    LokiCreateRequest | PrometheusCreateRequest | TempoCreateRequest | GitHubCreateRequest,
    Field(discriminator="kind"),
]

# The config fields each kind stores, so a PATCH can't set a field its kind doesn't use.
_TELEMETRY_FIELDS = frozenset({"url", "service_label", "org_id"})
CONFIG_FIELDS: dict[IntegrationKind, frozenset[str]] = {
    "loki": _TELEMETRY_FIELDS,
    "prometheus": _TELEMETRY_FIELDS,
    "tempo": _TELEMETRY_FIELDS,
    "github": frozenset({"url", "repository"}),
}


class IntegrationConfigUpdate(_Strict):
    """Settings to change. Omitted fields keep their value; `org_id: null` clears it."""

    url: str | None = Field(default=None, max_length=2048)
    service_label: str | None = Field(
        default=None, min_length=1, max_length=100, pattern=SERVICE_LABEL_PATTERN
    )
    org_id: str | None = Field(default=None, min_length=1, max_length=200)
    repository: str | None = Field(
        default=None, min_length=3, max_length=200, pattern=REPOSITORY_PATTERN
    )

    @field_validator("url")
    @classmethod
    def _check_url(cls, url: str | None) -> str | None:
        return None if url is None else check_backend_url(url)

    @model_validator(mode="after")
    def _required_fields_not_null(self) -> Self:
        for name in ("url", "service_label", "repository"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class IntegrationUpdateRequest(_Strict):
    """Payload for ``PATCH /v1/integrations/{id}``.

    Without `auth` the stored credential is kept, since the client never sees it. With `auth`
    the whole credential is replaced, so a username can't end up paired with the old password.
    """

    config: IntegrationConfigUpdate | None = None
    auth: IntegrationAuth | None = None

    @model_validator(mode="after")
    def _changes_something(self) -> Self:
        if self.auth is None and (self.config is None or not self.config.model_fields_set):
            raise ValueError("nothing to update: send config, auth or both")
        return self


class IntegrationSummary(BaseModel):
    """An integration as shown to its owner. The credential is never returned."""

    id: UUID
    kind: IntegrationKind
    config: dict[str, Any]
    has_secret: bool
    status: IntegrationStatus
    last_tested_at: AwareDatetime | None = None
    last_error: str | None = None
    created_at: AwareDatetime


class IntegrationList(BaseModel):
    """Response for ``GET /v1/integrations``: all of the user's integrations, one per kind."""

    items: list[IntegrationSummary]
