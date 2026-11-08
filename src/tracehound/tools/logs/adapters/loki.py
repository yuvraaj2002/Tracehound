"""Log source for Grafana Loki: one LogQL range query over HTTP, mapped to ``LogLine``."""

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta

import httpx

from tracehound.schemas.logs import LogLine
from tracehound.tools.logs.base import LogSource
from tracehound.tools.logs.dedupe import dedupe_by_message

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

# Case-insensitive line filter: matches JSON ("level":"error") and plain-text warnings alike.
_WARN_ERROR_PATTERN = r"(?i)\b(warn(ing)?|err(or)?|fatal|critical|panic|exception)\b"


class LokiLogSource(LogSource):
    """Reads WARN/ERROR-ish log lines from Loki's ``/loki/api/v1/query_range``.

    Services are matched on one stream label (``service_name`` by default, which Loki sets from
    OpenTelemetry's ``service.name``). A LogQL line filter keeps warn/error-like lines so INFO
    noise never leaves Loki. Lines that are JSON objects supply level, message and trace ID;
    anything else is kept as the raw message. Loki has no line IDs, so each line gets a stable ID
    hashed from its labels, timestamp and text.
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
        """WARN/ERROR-ish lines from ``services`` with ``start <= timestamp <= end``, oldest first."""
        if not services:
            return []
        # Backtick strings are raw in LogQL, so only regex metacharacters need escaping.
        names = "|".join(re.escape(s) for s in sorted(services))
        query = f"{{{self._service_label}=~`{names}`}} |~ `{_WARN_ERROR_PATTERN}`"
        # Loki's end is exclusive; nudge past ``end`` so our window stays inclusive.
        lines = self._query(query, start, end + timedelta(microseconds=1))
        return dedupe_by_message(sorted(lines, key=lambda line: line.timestamp))

    def _query(self, query: str, start: datetime, end: datetime) -> list[LogLine]:
        """Run one Loki ``query_range`` over ``[start, end)`` and map each hit to a ``LogLine``.

        ``end`` is exclusive here, matching Loki's API. Callers that want an inclusive window
        should pass a timestamp just past the last moment they care about.
        """
        response = self._client.get(
            "/loki/api/v1/query_range",
            params={
                "query": query,
                # Loki wants Unix time in nanoseconds, not a datetime / seconds float.
                "start": int(start.timestamp()) * 1_000_000_000 + start.microsecond * 1000,
                "end": int(end.timestamp()) * 1_000_000_000 + end.microsecond * 1000,
                "limit": self._limit,
                "direction": "forward",
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
        """Convert one Loki stream value into our canonical ``LogLine``.

        Prefers fields from a JSON log body, then stream labels. Invents a stable ``id`` because
        Loki does not provide one. Unknown JSON keys land in ``attributes``.
        """
        try:
            value = json.loads(text)
        except ValueError:
            value = None
        parsed = value if isinstance(value, dict) else {}
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
