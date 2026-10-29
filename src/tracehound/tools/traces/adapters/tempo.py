"""Trace source for Grafana Tempo: a TraceQL search, then each trace by ID, mapped to ``Span``."""

import base64
import hashlib
import math
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from tracehound.schemas.telemetry import Span
from tracehound.tools.traces.base import TraceSource


class TempoTraceSource(TraceSource):
    """Reads spans from Tempo's ``/api/search`` and ``/api/v2/traces/{id}``.

    The search finds up to ``limit`` traces that touch one of the services in the window, then
    each trace is fetched whole so parent links survive. That is a sample, not every trace: busy
    services have far more traces than an agent can read. Services are matched on the
    ``service.name`` resource attribute. Tempo has no span record IDs, so each span gets a stable
    ID hashed from its trace and span IDs.
    """

    def __init__(
        self,
        client: httpx.Client,
        service_attribute: str = "service.name",
        limit: int = 20,
    ) -> None:
        self._client = client  # base_url, auth headers and tenant (X-Scope-OrgID) set by caller
        self._service_attribute = service_attribute
        self._limit = limit

    def fetch(self, services: set[str], start: datetime, end: datetime) -> list[Span]:
        """Spans from ``services`` with ``start <= span.start <= end``, oldest first.

        Raises ``ValueError`` if Tempo returns a body without the expected fields.
        """
        if not services:
            return []
        spans = [
            span
            for trace_id in self._search(services, start, end)
            for span in self._trace(trace_id)
            if span.service in services and start <= span.start <= end
        ]
        return sorted(spans, key=lambda s: (s.start, s.id))

    def _traceql(self, services: set[str]) -> str:
        attribute = f"resource.{self._service_attribute}"
        matchers = " || ".join(f"{attribute} = {_quote(s)}" for s in sorted(services))
        return f"{{ {matchers} }}"

    def _search(self, services: set[str], start: datetime, end: datetime) -> list[str]:
        response = self._client.get(
            "/api/search",
            params={
                "q": self._traceql(services),
                "start": math.floor(
                    start.timestamp()
                ),  # whole seconds, widened to cover the window
                "end": math.ceil(end.timestamp()),
                "limit": self._limit,
            },
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body.get("traces"), list):
            raise ValueError(f"unexpected Tempo search response: {str(body)[:200]}")
        return list(dict.fromkeys(t["traceID"] for t in body["traces"]))

    def _trace(self, trace_id: str) -> list[Span]:
        response = self._client.get(f"/api/v2/traces/{trace_id}")
        response.raise_for_status()
        body = response.json()
        trace = body.get("trace")
        if not isinstance(trace, dict):
            raise ValueError(f"unexpected Tempo trace response: {str(body)[:200]}")
        return [
            self._to_span(
                raw, _service(resource_spans.get("resource", {}), self._service_attribute)
            )
            for resource_spans in trace.get("resourceSpans", [])
            for scope_spans in resource_spans.get("scopeSpans", [])
            for raw in scope_spans.get("spans", [])
        ]

    @staticmethod
    def _to_span(raw: dict[str, Any], service: str) -> Span:
        trace_id = _hex_id(raw["traceId"], 16)
        span_id = _hex_id(raw["spanId"], 8)
        parent = raw.get("parentSpanId")
        start_ns = int(raw["startTimeUnixNano"])
        end_ns = int(raw.get("endTimeUnixNano", start_ns))
        status = raw.get("status", {})
        failed = status.get("code") in ("STATUS_CODE_ERROR", 2)
        digest = hashlib.sha256(f"{trace_id}|{span_id}".encode()).hexdigest()
        return Span(
            id=f"tempo-{digest[:16]}",
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=_hex_id(parent, 8) if parent else None,
            service=service,
            name=raw.get("name", ""),
            start=_from_nanos(start_ns),
            duration_ms=max(end_ns - start_ns, 0) / 1e6,
            status="error" if failed else "ok",
            error=(status.get("message") or None) if failed else None,
        )


def _quote(value: str) -> str:
    """A TraceQL string literal."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _service(resource: dict[str, Any], attribute: str) -> str:
    for attr in resource.get("attributes", []):
        if attr.get("key") == attribute:
            return str(attr.get("value", {}).get("stringValue", "unknown"))
    return "unknown"


def _hex_id(value: str, size: int) -> str:
    """Tempo's OTLP JSON encodes IDs as base64 bytes; some versions and proxies send hex."""
    if len(value) == size * 2:
        try:
            bytes.fromhex(value)
            return value.lower()
        except ValueError:
            pass
    return base64.b64decode(value).hex()


def _from_nanos(nanos: int) -> datetime:
    seconds, rest = divmod(nanos, 1_000_000_000)
    return datetime.fromtimestamp(seconds, tz=UTC) + timedelta(microseconds=rest // 1000)
