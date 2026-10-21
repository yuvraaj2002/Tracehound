"""The interface every log backend adapter implements."""

from datetime import datetime
from typing import Protocol

from tracehound.schemas.telemetry import LogLine


class LogSource(Protocol):
    """Fetches log lines from one backend and returns them as canonical ``LogLine``s."""

    def fetch(self, services: set[str], start: datetime, end: datetime) -> list[LogLine]:
        """Lines from ``services`` with ``start <= timestamp <= end``, oldest first."""
        ...
