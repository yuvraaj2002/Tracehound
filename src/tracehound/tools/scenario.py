"""Read-only telemetry backed by a pinned scenario directory."""

import json
from datetime import datetime
from functools import cached_property
from pathlib import Path

from pydantic import TypeAdapter

from tracehound.schemas.telemetry import Deploy, Topology

_DEPLOYS = TypeAdapter(list[Deploy])


class ScenarioTelemetry:
    """Serves ``scenarios/<id>/*.json``. Never reads ``ground_truth/``."""

    def __init__(self, scenario_dir: Path) -> None:
        self._dir = scenario_dir

    def topology(self) -> Topology:
        return self._topology

    def deploys(self, services: set[str], start: datetime, end: datetime) -> list[Deploy]:
        """Deploys to ``services`` with ``start <= deployed_at <= end``, oldest first."""
        return [d for d in self._deploys if d.service in services and start <= d.deployed_at <= end]

    @cached_property
    def _topology(self) -> Topology:
        return Topology.model_validate(self._load("topology.json"))

    @cached_property
    def _deploys(self) -> list[Deploy]:
        return sorted(_DEPLOYS.validate_python(self._load("deploys.json")), key=_deployed_at)

    def _load(self, name: str) -> object:
        return json.loads((self._dir / name).read_text())


def _deployed_at(deploy: Deploy) -> datetime:
    return deploy.deployed_at
