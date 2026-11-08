"""Canonical deploy records as the deploy tools return them."""

from datetime import UTC, datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class Deploy(BaseModel):
    """A deployment of one service version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    service: str
    version: str
    previous_version: str | None
    deployed_at: AwareDatetime
    author: str
    commit: str
    change_summary: str
    config_diff: dict[str, dict[str, str | None]] = Field(
        default_factory=dict, description='Config key -> {"old": ..., "new": ...}'
    )

    @field_validator("deployed_at")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)
