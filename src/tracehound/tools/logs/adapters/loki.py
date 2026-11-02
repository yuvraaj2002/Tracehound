"""Log source for Grafana Loki: one LogQL range query over HTTP, mapped to ``LogLine``."""

import hashlib
import json
import logging
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

logger = logging.getLogger(__name__)

# Case-insensitive line filter that matches JSON ("level":"error") and plain-text logs alike.
_ERROR_PATTERN = r"(?i)\b(warn(ing)?|err(or)?|fatal|critical|panic|exception)\b"


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
        context_lines: int = 100,
    ) -> None:
        self._client = client  # base_url, auth headers and tenant (X-Scope-OrgID) set by caller
        self._service_label = service_label
        self._limit = limit
        self._context_lines = context_lines

    def fetch(self, services: set[str], start: datetime, end: datetime) -> list[LogLine]:
        """WARN/ERROR lines from ``services`` in ``[start, end]`` plus lead-in context.

        Two queries: every line matching an error-ish pattern, then the last ``context_lines``
        lines of any level just before the first of those (or before ``end`` if there are none),
        which usually hold the change that preceded the failure. If the error query alone hits
        ``limit`` the earliest ``limit`` lines are kept, since they are closest to the root cause.
        """
        if not services:
            return []
        selector = self._selector(services)
        after_end = end + timedelta(microseconds=1)  # Loki's end is exclusive
        errors = self._query(f"{selector} |~ `{_ERROR_PATTERN}`", start, after_end, "forward")
        if len(errors) >= self._limit:
            logger.warning(
                "Loki error query hit the %d-line limit; keeping the earliest", self._limit
            )
        errors.sort(key=lambda line: line.timestamp)
        context_end = errors[0].timestamp if errors else after_end
        context = (
            self._query(selector, start, context_end, "backward", self._context_lines)
            if self._context_lines > 0
            else []
        )
        merged = {line.id: line for line in [*context, *errors]}
        return sorted(merged.values(), key=lambda line: line.timestamp)

    def _selector(self, services: set[str]) -> str:
        # Backtick strings are raw in LogQL, so only regex metacharacters need escaping.
        names = "|".join(re.escape(s) for s in sorted(services))
        return f"{{{self._service_label}=~`{names}`}}"

    def _query(
        self,
        query: str,
        start: datetime,
        end: datetime,
        direction: str,
        limit: int | None = None,
    ) -> list[LogLine]:
        """One range query over ``[start, end)``, as in Loki."""
        response = self._client.get(
            "/loki/api/v1/query_range",
            params={
                "query": query,
                "start": _nanos(start),
                "end": _nanos(end),
                "limit": limit or self._limit,
                "direction": direction,
            },
        )
        response.raise_for_status()
        body = response.json()
        if body.get("status") != "success" or body["data"]["resultType"] != "streams":
            raise ValueError(f"unexpected Loki response: {str(body)[:200]}")
        return [
            self._to_line(stream["stream"], ts, text)
            for stream in body["data"]["result"]
            for ts, text, *_ in stream["values"]
        ]

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
