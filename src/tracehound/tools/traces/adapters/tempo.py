"""Trace source for Grafana Tempo: a TraceQL search, then each trace by ID, mapped to ``Span``."""

import base64
import hashlib
import math
from datetime import UTC, datetime, timedelta

import httpx

from tracehound.schemas.traces import Span
from tracehound.tools.source import TraceSource


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

        def quote(value: str) -> str:
            return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

        attribute = f"resource.{self._service_attribute}"
        matchers = " || ".join(f"{attribute} = {quote(s)}" for s in sorted(services))
        response = self._client.get(
            "/api/search",
            params={
                "q": f"{{ {matchers} }}",
                "start": math.floor(start.timestamp()),  # whole seconds, covers the window
                "end": math.ceil(end.timestamp()),
                "limit": self._limit,
            },
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body.get("traces"), list):
            raise ValueError(f"unexpected Tempo search response: {str(body)[:200]}")
        trace_ids = list(dict.fromkeys(t["traceID"] for t in body["traces"]))

        spans = [
            span
            for trace_id in trace_ids
            for span in self._spans(trace_id)
            if span.service in services and start <= span.start <= end
        ]
        return sorted(spans, key=lambda s: (s.start, s.id))

    def _spans(self, trace_id: str) -> list[Span]:
        """Fetch one Tempo trace and map every OTLP span to a canonical ``Span``."""

        def hex_id(value: str, size: int) -> str:
            # Tempo's OTLP JSON encodes IDs as base64; some versions and proxies send hex.
            if len(value) == size * 2:
                try:
                    bytes.fromhex(value)
                    return value.lower()
                except ValueError:
                    pass
            return base64.b64decode(value).hex()

        response = self._client.get(f"/api/v2/traces/{trace_id}")
        response.raise_for_status()
        body = response.json()
        trace = body.get("trace")
        if not isinstance(trace, dict):
            raise ValueError(f"unexpected Tempo trace response: {str(body)[:200]}")

        out: list[Span] = []
        for resource_spans in trace.get("resourceSpans", []):
            service = "unknown"
            for attr in resource_spans.get("resource", {}).get("attributes", []):
                if attr.get("key") == self._service_attribute:
                    service = str(attr.get("value", {}).get("stringValue", "unknown"))
                    break
            for scope_spans in resource_spans.get("scopeSpans", []):
                for raw in scope_spans.get("spans", []):
                    tid = hex_id(raw["traceId"], 16)
                    sid = hex_id(raw["spanId"], 8)
                    parent = raw.get("parentSpanId")
                    start_ns = int(raw["startTimeUnixNano"])
                    end_ns = int(raw.get("endTimeUnixNano", start_ns))
                    status = raw.get("status", {})
                    failed = status.get("code") in ("STATUS_CODE_ERROR", 2)
                    seconds, rest = divmod(start_ns, 1_000_000_000)
                    digest = hashlib.sha256(f"{tid}|{sid}".encode()).hexdigest()
                    out.append(
                        Span(
                            id=f"tempo-{digest[:16]}",
                            trace_id=tid,
                            span_id=sid,
                            parent_span_id=hex_id(parent, 8) if parent else None,
                            service=service,
                            name=raw.get("name", ""),
                            start=datetime.fromtimestamp(seconds, tz=UTC)
                            + timedelta(microseconds=rest // 1000),
                            duration_ms=max(end_ns - start_ns, 0) / 1e6,
                            status="error" if failed else "ok",
                            error=(status.get("message") or None) if failed else None,
                        )
                    )
        return out
