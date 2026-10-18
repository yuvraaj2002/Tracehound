"""Read-only telemetry from a pinned scenario directory. Never reads ``ground_truth/``."""

import json
from datetime import datetime
from pathlib import Path

from pydantic import TypeAdapter

from tracehound.schemas.telemetry import Deploy, Topology

_DEPLOYS = TypeAdapter(list[Deploy])


def load_topology(scenario_dir: Path) -> Topology:
    return Topology.model_validate(_load(scenario_dir / "topology.json"))


def load_deploys(
    scenario_dir: Path, services: set[str], start: datetime, end: datetime
) -> list[Deploy]:
    """Deploys to ``services`` with ``start <= deployed_at <= end``, oldest first."""
    deploys = _DEPLOYS.validate_python(_load(scenario_dir / "deploys.json"))
    matching = [d for d in deploys if d.service in services and start <= d.deployed_at <= end]
    return sorted(matching, key=lambda d: d.deployed_at)


def _load(path: Path) -> object:
    return json.loads(path.read_text())
