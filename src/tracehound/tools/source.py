"""Fetch contracts: one generic ``Source``, plus a thin subclass per domain."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Generic, TypeVar

from tracehound.schemas.deploys import Deploy
from tracehound.schemas.logs import LogLine
from tracehound.schemas.metrics import MetricSeries
from tracehound.schemas.traces import Span

T = TypeVar("T")


class Source(ABC, Generic[T]):
    """Fetches records from one backend for the given services and time window.

    Each adapter's ``__init__`` takes whatever its backend needs (a path, an HTTP client, ...),
    so only ``fetch`` is part of the contract.
    """

    @abstractmethod
    def fetch(self, services: set[str], start: datetime, end: datetime) -> list[T]:
        """Records from ``services`` in ``[start, end]``, oldest first unless noted by the domain."""


class LogSource(Source[LogLine]):
    """Fetches log lines from one backend and returns them as canonical ``LogLine``s.

    ``fetch`` returns lines from ``services`` with ``start <= timestamp <= end``, oldest first.
    """


class MetricSource(Source[MetricSeries]):
    """Fetches time series from one backend and returns them as canonical ``MetricSeries``.

    ``fetch`` returns series from ``services`` with points where ``start <= timestamp <= end``.
    Series with no points in the window are dropped.
    """


class TraceSource(Source[Span]):
    """Fetches spans from one backend and returns them as canonical ``Span``s.

    ``fetch`` returns spans from ``services`` with ``start <= span.start <= end``, oldest first.
    """


class DeploySource(Source[Deploy]):
    """Fetches deployments from one backend and returns them as canonical ``Deploy``s.

    ``fetch`` returns deploys to ``services`` with ``start <= deployed_at <= end``, oldest first.
    """
