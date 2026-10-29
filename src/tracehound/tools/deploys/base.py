"""The base class every deploy backend adapter extends."""

from abc import ABC, abstractmethod
from datetime import datetime

from tracehound.schemas.telemetry import Deploy


class DeploySource(ABC):
    """Fetches deployments from one backend and returns them as canonical ``Deploy``s.

    Each adapter's ``__init__`` takes whatever its backend needs (a path, an HTTP client, ...),
    so only ``fetch`` is part of the contract.
    """

    @abstractmethod
    def fetch(self, services: set[str], start: datetime, end: datetime) -> list[Deploy]:
        """Deploys to ``services`` with ``start <= deployed_at <= end``, oldest first."""
