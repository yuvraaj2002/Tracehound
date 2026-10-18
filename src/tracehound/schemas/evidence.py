"""Evidence contracts: immutable, cited references to telemetry records."""

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, field_validator

EvidenceId = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")]
"""Identifier of the source record, e.g. ``log-006`` or ``dep-002``."""


class EvidenceSource(StrEnum):
    LOG = "log"
    METRIC = "metric"
    TRACE = "trace"
    DEPLOY = "deploy"


def hash_payload(payload: Mapping[str, JsonValue]) -> str:
    """SHA-256 of the canonical JSON form, so equal records hash equally."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


class Evidence(BaseModel):
    """A telemetry record an agent may cite. The raw record stays at ``source_locator``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: EvidenceId
    incident_id: UUID
    source_type: EvidenceSource
    source_locator: str = Field(min_length=1, max_length=512)
    service: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    event_time: AwareDatetime
    collected_at: AwareDatetime
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    excerpt: str = Field(min_length=1, max_length=2000)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("event_time", "collected_at")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)
