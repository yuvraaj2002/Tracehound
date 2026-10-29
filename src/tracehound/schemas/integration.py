"""Integration contracts: a user's connection to a telemetry backend (Loki first)."""

import ipaddress
import os
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr, field_validator

IntegrationKind = Literal["loki"]
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


class LokiConfig(_Strict):
    """Non-secret Loki settings. `org_id` is sent as `X-Scope-OrgID` for multi-tenant Loki."""

    url: str = Field(max_length=2048)
    service_label: str = Field(
        default="service_name", min_length=1, max_length=100, pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$"
    )
    org_id: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("url")
    @classmethod
    def _check_url(cls, url: str) -> str:
        return check_backend_url(url)


class IntegrationCreateRequest(_Strict):
    """Payload for ``POST /v1/integrations``. The credential in `auth` is stored encrypted."""

    kind: IntegrationKind
    config: LokiConfig
    auth: IntegrationAuth


class IntegrationSummary(BaseModel):
    """An integration as shown to its owner. The credential is never returned."""

    id: UUID
    kind: IntegrationKind
    config: dict[str, Any]
    has_secret: bool
    status: IntegrationStatus
    last_tested_at: AwareDatetime | None = None
    created_at: AwareDatetime


class IntegrationList(BaseModel):
    """Response for ``GET /v1/integrations``: all of the user's integrations, one per kind."""

    items: list[IntegrationSummary]
