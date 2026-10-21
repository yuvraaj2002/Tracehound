"""Log source for Grafana Loki (LogQL over HTTP). Not implemented yet."""

from datetime import datetime

from tracehound.schemas.telemetry import LogLine


class LokiLogSource:
    """Fetches log lines from Grafana Loki (LogQL over HTTP) and maps them to ``LogLine``."""

    def fetch(self, services: set[str], start: datetime, end: datetime) -> list[LogLine]:
        raise NotImplementedError
