"""Log source for Elasticsearch and OpenSearch. Not implemented yet."""

from datetime import datetime

from tracehound.schemas.telemetry import LogLine


class ElasticLogSource:
    """Fetches log lines from Elasticsearch and OpenSearch and maps them to ``LogLine``."""

    def fetch(self, services: set[str], start: datetime, end: datetime) -> list[LogLine]:
        raise NotImplementedError
