"""File metric source: a pinned scenario's ``metrics.json``. Never reads ``ground_truth/``."""

import json
from datetime import datetime
from pathlib import Path

from pydantic import TypeAdapter

from tracehound.schemas.telemetry import MetricSeries
from tracehound.tools.metrics.base import MetricSource

_SERIES = TypeAdapter(list[MetricSeries])


class FileMetricSource(MetricSource):
    """Reads the scenario's ``metrics.json`` once and answers queries by service and time."""

    def __init__(self, scenario_dir: Path) -> None:
        self._series = _SERIES.validate_python(
            json.loads((scenario_dir / "metrics.json").read_text())
        )

    def fetch(self, services: set[str], start: datetime, end: datetime) -> list[MetricSeries]:
        """Series from ``services``, keeping only points with ``start <= timestamp <= end``.

        Series with no points left are dropped.
        """
        result = []
        for series in self._series:
            if series.service not in services:
                continue
            points = [p for p in series.points if start <= p.timestamp <= end]
            if points:
                result.append(series.model_copy(update={"points": points}))
        return result
