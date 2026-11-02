from datetime import UTC, datetime
from typing import Any

import httpx

from tracehound.tools.logs import LokiLogSource

START = datetime(2026, 10, 15, 13, 45, tzinfo=UTC)
END = datetime(2026, 10, 15, 13, 50, tzinfo=UTC)
BASE = int(START.timestamp()) * 1_000_000_000


def _entry(second: int, text: str, service: str = "orders") -> tuple[dict[str, str], list[str]]:
    return {"service_name": service}, [str(BASE + second * 1_000_000_000), text]


def _source(
    error_lines: list[Any], earlier_lines: list[Any], requests: list[httpx.Request], **kwargs: Any
) -> LokiLogSource:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        entries = error_lines if "|~" in request.url.params["query"] else earlier_lines
        result = [{"stream": labels, "values": [value]} for labels, value in entries]
        return httpx.Response(
            200, json={"status": "success", "data": {"resultType": "streams", "result": result}}
        )

    client = httpx.Client(base_url="http://loki", transport=httpx.MockTransport(handler))
    return LokiLogSource(client, **kwargs)


def test_fetches_errors_then_context_ending_at_first_error() -> None:
    requests: list[httpx.Request] = []
    errors = [_entry(30, "connection pool exhausted"), _entry(20, "slow query")]
    context = [_entry(10, "deploy started"), _entry(15, "config reloaded")]
    lines = _source(errors, context, requests).fetch({"orders", "orders-db"}, START, END)

    assert [line.message for line in lines] == [
        "deploy started",
        "config reloaded",
        "slow query",
        "connection pool exhausted",
    ]
    error_query, context_query = (r.url.params for r in requests)
    assert error_query["query"].startswith("{service_name=~`orders|orders\\-db`} |~ `")
    assert error_query["direction"] == "forward"
    assert context_query["query"] == "{service_name=~`orders|orders\\-db`}"
    assert context_query["direction"] == "backward"
    assert context_query["limit"] == "100"
    assert int(context_query["end"]) == BASE + 20 * 1_000_000_000  # first error, exclusive


def test_without_errors_context_runs_to_the_window_end() -> None:
    requests: list[httpx.Request] = []
    lines = _source([], [_entry(5, "all quiet")], requests).fetch({"orders"}, START, END)

    assert [line.message for line in lines] == ["all quiet"]
    assert int(requests[1].url.params["end"]) > int(END.timestamp()) * 1_000_000_000


def test_duplicate_lines_between_queries_are_kept_once() -> None:
    same = _entry(20, "slow query")
    lines = _source([same], [same], []).fetch({"orders"}, START, END)

    assert len(lines) == 1


def test_hitting_the_limit_keeps_the_earliest_errors_instead_of_failing() -> None:
    errors = [_entry(second, f"error {second}") for second in (3, 1, 2)]
    lines = _source(errors, [], [], limit=3).fetch({"orders"}, START, END)

    assert [line.message for line in lines] == ["error 1", "error 2", "error 3"]


def test_context_can_be_turned_off() -> None:
    requests: list[httpx.Request] = []
    _source([_entry(1, "error")], [], requests, context_lines=0).fetch({"orders"}, START, END)

    assert len(requests) == 1


def test_no_services_makes_no_request() -> None:
    requests: list[httpx.Request] = []
    assert _source([], [], requests).fetch(set(), START, END) == []
    assert requests == []
