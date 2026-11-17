"""Log source for Grafana Loki: one LogQL range query over HTTP, mapped to ``LogLine``."""

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta

import httpx

from tracehound.schemas.logs import LogLine
from tracehound.tools.source import LogSource
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

# Loki's ingest-time discover_log_levels (default on) writes structured metadata
# ``detected_level`` with these normalized lowercase values. Hard lane filters on them —
# not with a line-body regex — so INFO that merely mentions "error" stays out of lane 1.
_HARD_DETECTED_LEVELS = "warn|error|fatal|critical"

# Soft lane (non-hard levels only): failure keywords in the line body. Keep this tight;
# softer words like "failed" / "denied" / "warn" are intentionally out for v1 noise control.
_SOFT_FAILURE_KEYWORDS = r"(?i)\b(error|exception|timeout|panic|fatal|critical)\b"


class LokiLogSource(LogSource):
    """Reads failure-biased log lines from Loki's ``/loki/api/v1/query_range``.

    Services are matched on one stream label (``service_name`` by default, which Loki sets from
    OpenTelemetry's ``service.name``). Fetch uses two lanes Loki cannot OR in one log query:

    * **Hard** — structured metadata ``detected_level`` ∈ warn|error|fatal|critical
    * **Soft** — other levels whose **line body** matches failure keywords

    Results are merged, capped to the ``limit`` most recent lines (default 2000), then
    deduped. Each Loki call uses ``direction=backward`` so a truncated lane prefers newest
    lines; after merge we keep the newest ``limit`` overall and return oldest→newest. Lines
    that are JSON objects supply level, message and trace ID; anything else is kept as the
    raw message. Loki has no line IDs, so each line gets a stable ID hashed from its labels,
    timestamp and text.
    """

    def __init__(
        self,
        client: httpx.Client,
        service_label: str = "service_name",
        limit: int = 2000,
    ) -> None:
        self._client = client  # base_url, auth headers and tenant (X-Scope-OrgID) set by caller
        self._service_label = service_label
        self._limit = limit

    def fetch(self, services: set[str], start: datetime, end: datetime) -> list[LogLine]:
        """Dual-lane failure-biased lines from ``services`` in ``[start, end]``, oldest first.

        When the merged set exceeds ``limit``, only the newest ``limit`` lines are kept.
        """
        if not services:
            return []
        # Backtick strings are raw in LogQL, so only regex metacharacters need escaping.
        names = "|".join(re.escape(s) for s in sorted(services))
        selector = f"{{{self._service_label}=~`{names}`}}"
        # ``detected_level`` is structured metadata — pipeline label filter, not inside {}.
        hard_query = f"{selector} | detected_level=~`{_HARD_DETECTED_LEVELS}`"
        # Soft lane: exclude hard severities, then grep the body for failure keywords.
        soft_query = (
            f"{selector} | detected_level!~`{_HARD_DETECTED_LEVELS}` "
            f"|~ `{_SOFT_FAILURE_KEYWORDS}`"
        )
        # Loki's end is exclusive; nudge past ``end`` so our window stays inclusive.
        window_end = end + timedelta(microseconds=1)
        by_id = {line.id: line for line in self._query(hard_query, start, window_end)}
        for line in self._query(soft_query, start, window_end):
            by_id.setdefault(line.id, line)
        # Newest-biased cap across both lanes, then present oldest→newest to the agent.
        ordered = sorted(by_id.values(), key=lambda line: line.timestamp)
        if len(ordered) > self._limit:
            ordered = ordered[-self._limit :]
        return dedupe_by_message(ordered)

    def _query(self, query: str, start: datetime, end: datetime) -> list[LogLine]:
        """Run one Loki ``query_range`` over ``[start, end)`` and map each hit to a ``LogLine``.

        ``end`` is exclusive here, matching Loki's API. Callers that want an inclusive window
        should pass a timestamp just past the last moment they care about. ``direction=backward``
        makes Loki prefer the newest lines when ``limit`` truncates a lane.
        """
        response = self._client.get(
            "/loki/api/v1/query_range",
            params={
                "query": query,
                # Loki wants Unix time in nanoseconds, not a datetime / seconds float.
                "start": int(start.timestamp()) * 1_000_000_000 + start.microsecond * 1000,
                "end": int(end.timestamp()) * 1_000_000_000 + end.microsecond * 1000,
                "limit": self._limit,
                "direction": "backward",
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
