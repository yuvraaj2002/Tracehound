"""Log tools: structured log lines from a pinned scenario. Never reads ``ground_truth/``."""

import json
from datetime import datetime
from pathlib import Path

from pydantic import TypeAdapter

from tracehound.schemas.telemetry import LogLine

_LOGS = TypeAdapter(list[LogLine])


class LogReader:
    """Reads the scenario's ``logs.json`` once and answers queries by service and time."""

    def __init__(self, scenario_dir: Path) -> None:
        self._lines = _LOGS.validate_python(json.loads((scenario_dir / "logs.json").read_text()))

    def fetch(self, services: set[str], start: datetime, end: datetime) -> list[LogLine]:
        """Lines from ``services`` with ``start <= timestamp <= end``, oldest first."""
        matching = [
            line
            for line in self._lines
            if line.service in services and start <= line.timestamp <= end
        ]
        return sorted(matching, key=lambda line: line.timestamp)
