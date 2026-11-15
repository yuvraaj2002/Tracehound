"""Generic fetch contract shared by every telemetry / change source."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Generic, TypeVar

T = TypeVar("T")


class Source(ABC, Generic[T]):
    """Fetches records from one backend for the given services and time window.

    Each adapter's ``__init__`` takes whatever its backend needs (a path, an HTTP client, ...),
    so only ``fetch`` is part of the contract. Domain modules subclass this with a concrete
    record type (``LogLine``, ``Deploy``, ...).
    """

    @abstractmethod
    def fetch(self, services: set[str], start: datetime, end: datetime) -> list[T]:
        """Records from ``services`` in ``[start, end]``, oldest first unless noted by the domain."""
