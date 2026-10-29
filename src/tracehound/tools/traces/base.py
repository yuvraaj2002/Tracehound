"""The base class every trace backend adapter extends."""

from abc import ABC, abstractmethod
from datetime import datetime

from tracehound.schemas.telemetry import Span


class TraceSource(ABC):
    """Fetches spans from one backend and returns them as canonical ``Span``s.

    Each adapter's ``__init__`` takes whatever its backend needs (a path, an HTTP client, ...),
    so only ``fetch`` is part of the contract.
    """

    @abstractmethod
    def fetch(self, services: set[str], start: datetime, end: datetime) -> list[Span]:
        """Spans from ``services`` with ``start <= span.start <= end``, oldest first."""
