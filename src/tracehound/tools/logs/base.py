"""The base class every log backend adapter extends."""

from abc import ABC, abstractmethod
from datetime import datetime

from tracehound.schemas.telemetry import LogLine


class LogSource(ABC):
    """Fetches log lines from one backend and returns them as canonical ``LogLine``s.

    Each adapter's ``__init__`` takes whatever its backend needs (a path, an HTTP client, ...),
    so only ``fetch`` is part of the contract.
    """

    @abstractmethod
    def fetch(self, services: set[str], start: datetime, end: datetime) -> list[LogLine]:
        """Lines from ``services`` with ``start <= timestamp <= end``, oldest first."""
