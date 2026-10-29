import base64
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from tracehound.tools.traces import TempoTraceSource

START = datetime(2026, 10, 15, 13, 45, tzinfo=UTC)
END = datetime(2026, 10, 15, 13, 47, tzinfo=UTC)
TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
NANOS = int(START.timestamp()) * 1_000_000_000


def _b64(hex_id: str) -> str:
    return base64.b64encode(bytes.fromhex(hex_id)).decode()


def _span(span_id: str, parent: str | None, offset_ms: int, **extra: Any) -> dict[str, Any]:
    start = NANOS + offset_ms * 1_000_000
    span = {
        "traceId": _b64(TRACE_ID),
        "spanId": _b64(span_id),
        "name": "db.pool.acquire",
        "startTimeUnixNano": str(start),
        "endTimeUnixNano": str(start + 2_003_000_000),
        "status": {},
        **extra,
    }
    if parent:
        span["parentSpanId"] = _b64(parent)
    return span


def _resource(service: str, *spans: dict[str, Any]) -> dict[str, Any]:
    return {
        "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": service}}]},
        "scopeSpans": [{"spans": list(spans)}],
    }


def _source(
    resource_spans: list[dict[str, Any]], requests: list[httpx.Request] | None = None
) -> TempoTraceSource:
    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        if request.url.path == "/api/search":
            return httpx.Response(200, json={"traces": [{"traceID": TRACE_ID}]})
        return httpx.Response(200, json={"trace": {"resourceSpans": resource_spans}})

    client = httpx.Client(base_url="http://tempo", transport=httpx.MockTransport(handler))
    return TempoTraceSource(client)


def test_builds_traceql_search_then_fetches_each_trace() -> None:
    requests: list[httpx.Request] = []
    _source([], requests).fetch({"orders-db", 'we"ird'}, START, END)

    params = requests[0].url.params
    assert requests[0].url.path == "/api/search"
    assert params["q"] == (
        '{ resource.service.name = "orders-db" || resource.service.name = "we\\"ird" }'
    )
    assert params["start"] == str(int(START.timestamp()))
    assert params["end"] == str(int(END.timestamp()))
    assert requests[1].url.path == f"/api/v2/traces/{TRACE_ID}"


def test_maps_otlp_spans_and_keeps_only_scoped_services_in_window() -> None:
    resource_spans = [
        _resource(
            "checkout-api",
            _span(
                "00f067aa0ba902b7",
                "b7ad6b7169203331",
                100,
                status={"code": "STATUS_CODE_ERROR", "message": "pool timeout"},
            ),
            _span("b7ad6b7169203331", None, 0),
            _span("1111111111111111", None, 10 * 60_000),  # after END
        ),
        _resource("payments-api", _span("2222222222222222", None, 50)),
    ]
    spans = _source(resource_spans).fetch({"checkout-api"}, START, END)

    assert [s.span_id for s in spans] == ["b7ad6b7169203331", "00f067aa0ba902b7"]
    root, child = spans
    assert root.parent_span_id is None and root.status == "ok" and root.error is None
    assert child.trace_id == TRACE_ID
    assert child.parent_span_id == "b7ad6b7169203331"
    assert (child.status, child.error) == ("error", "pool timeout")
    assert child.duration_ms == 2003
    assert child.start == datetime(2026, 10, 15, 13, 45, 0, 100_000, tzinfo=UTC)
    assert child.id.startswith("tempo-")


def test_ids_are_stable_and_hex_ids_are_accepted() -> None:
    span = _span("b7ad6b7169203331", None, 0) | {
        "traceId": TRACE_ID.upper(),
        "spanId": "b7ad6b7169203331",
    }
    first = _source([_resource("checkout-api", span)]).fetch({"checkout-api"}, START, END)
    second = _source([_resource("checkout-api", span)]).fetch({"checkout-api"}, START, END)

    assert first[0].trace_id == TRACE_ID
    assert first[0].id == second[0].id


def test_no_services_makes_no_request() -> None:
    requests: list[httpx.Request] = []
    assert _source([], requests).fetch(set(), START, END) == []
    assert requests == []


def test_unexpected_search_response_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "bad query"})

    client = httpx.Client(base_url="http://tempo", transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="unexpected Tempo search response"):
        TempoTraceSource(client).fetch({"checkout-api"}, START, END)
