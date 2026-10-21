"""Log source for AWS CloudWatch Logs (Logs Insights queries). Not implemented yet."""

from datetime import datetime

from tracehound.schemas.telemetry import LogLine


class CloudWatchLogSource:
    """Fetches log lines from CloudWatch Logs Insights and maps them to ``LogLine``."""

    def fetch(self, services: set[str], start: datetime, end: datetime) -> list[LogLine]:
        raise NotImplementedError
