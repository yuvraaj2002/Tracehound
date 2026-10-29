"""File deploy source: a pinned scenario's ``deploys.json``. Never reads ``ground_truth/``."""

from datetime import datetime
from pathlib import Path

from tracehound.schemas.telemetry import Deploy
from tracehound.tools.deploys.base import DeploySource
from tracehound.tools.triage import load_deploys


class FileDeploySource(DeploySource):
    """Answers deploy queries by service and time for one scenario."""

    def __init__(self, scenario_dir: Path) -> None:
        self._scenario_dir = scenario_dir

    def fetch(self, services: set[str], start: datetime, end: datetime) -> list[Deploy]:
        """Deploys to ``services`` with ``start <= deployed_at <= end``, oldest first."""
        return load_deploys(self._scenario_dir, services, start, end)
