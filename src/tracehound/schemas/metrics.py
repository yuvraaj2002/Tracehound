"""Canonical metric records as the metric tools return them."""

from datetime import UTC, datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, field_validator


class MetricPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    timestamp: AwareDatetime
    value: float

    @field_validator("timestamp")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class MetricSeries(BaseModel):
    """One time series, such as checkout-api p95 latency, sampled every minute."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    service: str
    name: str
    unit: str
    points: list[MetricPoint]
