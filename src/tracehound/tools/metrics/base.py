"""The base class every metric backend adapter extends."""

from abc import ABC, abstractmethod
from datetime import datetime

from tracehound.schemas.telemetry import MetricSeries


class MetricSource(ABC):
    """Fetches time series from one backend and returns them as canonical ``MetricSeries``.

    Each adapter's ``__init__`` takes whatever its backend needs (a path, an HTTP client, ...),
    so only ``fetch`` is part of the contract.
    """

    @abstractmethod
    def fetch(self, services: set[str], start: datetime, end: datetime) -> list[MetricSeries]:
        """Series from ``services`` with points where ``start <= timestamp <= end``.

        Series with no points in the window are dropped.
        """
