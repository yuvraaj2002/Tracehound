"""Trace tools: spans from a pinned scenario. Never reads ``ground_truth/``."""

import json
from datetime import datetime
from pathlib import Path

from pydantic import TypeAdapter

from tracehound.schemas.telemetry import Span

_SPANS = TypeAdapter(list[Span])


class TraceReader:
    """Reads the scenario's ``traces.json`` once and answers queries by service and time."""

    def __init__(self, scenario_dir: Path) -> None:
        self._spans = _SPANS.validate_python(json.loads((scenario_dir / "traces.json").read_text()))

    def fetch(self, services: set[str], start: datetime, end: datetime) -> list[Span]:
        """Spans from ``services`` with ``start <= span.start <= end``, oldest first."""
        return sorted(
            (s for s in self._spans if s.service in services and start <= s.start <= end),
            key=lambda s: (s.start, s.id),
        )
