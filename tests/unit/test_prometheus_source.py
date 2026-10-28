from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from tracehound.tools.metrics import MetricQuery, PrometheusMetricSource

START = datetime(2026, 10, 15, 13, 45, tzinfo=UTC)
END = datetime(2026, 10, 15, 13, 47, tzinfo=UTC)
QUERY = MetricQuery(name="http_request_rate", unit="req/s", promql="sum by ($label) (x{$selector})")


def _source(result: list[dict[str, Any]], requests: list[httpx.Request] | None = None) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        body = {"status": "success", "data": {"resultType": "matrix", "result": result}}
        return httpx.Response(200, json=body)

    client = httpx.Client(base_url="http://prom", transport=httpx.MockTransport(handler))
    return PrometheusMetricSource(client, queries=(QUERY,))


def _values(*values: str) -> list[list[Any]]:
    return [[START.timestamp() + 60 * i, v] for i, v in enumerate(values)]


def test_builds_promql_with_service_matcher_and_range_params() -> None:
    requests: list[httpx.Request] = []
    _source([], requests).fetch({"orders-db", "checkout-api"}, START, END)

    params = requests[0].url.params
    assert requests[0].url.path == "/api/v1/query_range"
    assert params["query"] == r"sum by (job) (x{job=~`checkout\-api|orders\-db`})"
    assert float(params["start"]) == START.timestamp()
    assert float(params["end"]) == END.timestamp()
    assert params["step"] == "60.0"


def test_maps_matrix_to_series_and_drops_nan_samples() -> None:
    result = [{"metric": {"job": "checkout-api"}, "values": _values("121.5", "NaN", "118")}]
    [series] = _source(result).fetch({"checkout-api"}, START, END)

    assert series.service == "checkout-api"
    assert (series.name, series.unit) == ("http_request_rate", "req/s")
    assert series.id.startswith("prom-")
    assert [p.value for p in series.points] == [121.5, 118.0]
    assert series.points[0].timestamp == START


def test_ids_are_stable_and_empty_series_are_dropped() -> None:
    result = [
        {"metric": {"job": "checkout-api"}, "values": _values("1")},
        {"metric": {"job": "orders-db"}, "values": _values("NaN")},
    ]
    first = _source(result).fetch({"checkout-api", "orders-db"}, START, END)
    second = _source(result).fetch({"checkout-api", "orders-db"}, START, END)

    assert [s.service for s in first] == ["checkout-api"]
    assert [s.id for s in first] == [s.id for s in second]


def test_no_services_makes_no_request() -> None:
    requests: list[httpx.Request] = []
    assert _source([], requests).fetch(set(), START, END) == []
    assert requests == []


def test_series_without_service_label_raises() -> None:
    with pytest.raises(ValueError, match="without 'job'"):
        _source([{"metric": {}, "values": _values("1")}]).fetch({"checkout-api"}, START, END)


def test_error_response_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "error", "error": "bad query"})

    client = httpx.Client(base_url="http://prom", transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="unexpected Prometheus response"):
        PrometheusMetricSource(client, queries=(QUERY,)).fetch({"checkout-api"}, START, END)
