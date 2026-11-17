"""Contract for the signed-in user's own profile."""

from uuid import UUID

from pydantic import BaseModel


class Me(BaseModel):
    """Response for ``GET /v1/me``: who the access token belongs to."""

    id: UUID
    email: str | None = None
    name: str | None = None
    avatar_url: str | None = None
