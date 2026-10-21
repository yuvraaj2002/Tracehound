"""Log source for Grafana Loki: one LogQL range query over HTTP, mapped to ``LogLine``."""

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from tracehound.schemas.telemetry import LogLine
from tracehound.tools.logs.base import LogSource

_LEVELS = {
    "trace": "DEBUG",
    "debug": "DEBUG",
    "info": "INFO",
    "notice": "INFO",
    "warn": "WARN",
    "warning": "WARN",
    "error": "ERROR",
    "err": "ERROR",
    "critical": "ERROR",
    "fatal": "ERROR",
}


class LokiLogSource(LogSource):
    """Reads log lines from Loki's ``/loki/api/v1/query_range``.

    Services are matched on one stream label (``service_name`` by default, which Loki sets from
    OpenTelemetry's ``service.name``). Lines that are JSON objects supply level, message and
    trace ID; anything else is kept as the raw message. Loki has no line IDs, so each line gets a
    stable ID hashed from its labels, timestamp and text.
    """

    def __init__(
        self,
        client: httpx.Client,
        service_label: str = "service_name",
        limit: int = 5000,
    ) -> None:
        self._client = client  # base_url, auth headers and tenant (X-Scope-OrgID) set by caller
        self._service_label = service_label
        self._limit = limit

    def fetch(self, services: set[str], start: datetime, end: datetime) -> list[LogLine]:
        """Lines from ``services`` with ``start <= timestamp <= end``, oldest first.

        Raises ``ValueError`` if Loki returns ``limit`` lines, since the rest were cut off.
        """
        if not services:
            return []
        response = self._client.get(
            "/loki/api/v1/query_range",
            params={
                "query": self._query(services),
                "start": _nanos(start),
                "end": _nanos(end + timedelta(microseconds=1)),  # Loki's end is exclusive
                "limit": self._limit,
                "direction": "forward",
            },
        )
        response.raise_for_status()
        body = response.json()
        if body.get("status") != "success" or body["data"]["resultType"] != "streams":
            raise ValueError(f"unexpected Loki response: {str(body)[:200]}")
        lines = [
            self._to_line(stream["stream"], ts, text)
            for stream in body["data"]["result"]
            for ts, text, *_ in stream["values"]
        ]
        if len(lines) >= self._limit:
            raise ValueError(f"Loki returned {len(lines)} lines, the limit; results are truncated")
        return sorted(lines, key=lambda line: line.timestamp)

    def _query(self, services: set[str]) -> str:
        # Backtick strings are raw in LogQL, so only regex metacharacters need escaping.
        names = "|".join(re.escape(s) for s in sorted(services))
        return f"{{{self._service_label}=~`{names}`}}"

    def _to_line(self, labels: dict[str, str], ts: str, text: str) -> LogLine:
        parsed = _json_object(text)
        level = parsed.get("level") or labels.get("level") or labels.get("detected_level")
        trace_id = parsed.get("trace_id") or parsed.get("traceId") or labels.get("trace_id")
        message = parsed.get("message") or parsed.get("msg") or text
        known = {"level", "message", "msg", "trace_id", "traceId", "timestamp", "time", "ts"}
        attributes = {k: v for k, v in parsed.items() if k not in known}
        digest = hashlib.sha256(f"{sorted(labels.items())}|{ts}|{text}".encode()).hexdigest()
        return LogLine(
            id=f"loki-{digest[:16]}",
            timestamp=datetime.fromtimestamp(int(ts) / 1e9, tz=UTC),
            service=labels[self._service_label],
            level=_LEVELS.get(str(level).lower(), "INFO"),
            message=str(message),
            trace_id=str(trace_id) if trace_id else None,
            attributes=attributes,
        )


def _nanos(moment: datetime) -> int:
    return int(moment.timestamp()) * 1_000_000_000 + moment.microsecond * 1000


def _json_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}
