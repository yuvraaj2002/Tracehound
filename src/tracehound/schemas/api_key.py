"""API key contracts."""

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class ApiKeyCreateRequest(BaseModel):
    """Payload for ``POST /v1/api-keys``."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)


class ApiKeyCreated(BaseModel):
    """Response for a new key. `key` is the raw key; it is returned here and never again."""

    id: UUID
    name: str
    key: str
    prefix: str
    suffix: str
    created_at: AwareDatetime


class ApiKeySummary(BaseModel):
    """A key as listed to its owner. The raw key is never returned after creation."""

    id: UUID
    name: str
    prefix: str
    suffix: str
    created_at: AwareDatetime
    last_used_at: AwareDatetime | None = None


class ApiKeyPage(BaseModel):
    """Response for ``GET /v1/api-keys``. Pass `next_cursor` back as `cursor` for the next page."""

    items: list[ApiKeySummary]
    next_cursor: str | None = None
