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
    entries: list[Any], requests: list[httpx.Request], **kwargs: Any
) -> LokiLogSource:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        result = [{"stream": labels, "values": [value]} for labels, value in entries]
        return httpx.Response(
            200, json={"status": "success", "data": {"resultType": "streams", "result": result}}
        )

    client = httpx.Client(base_url="http://loki", transport=httpx.MockTransport(handler))
    return LokiLogSource(client, **kwargs)


def test_fetches_warn_error_lines_in_inclusive_window_oldest_first() -> None:
    requests: list[httpx.Request] = []
    entries = [
        _entry(30, "error: connection pool exhausted"),
        _entry(10, "warning: deploy started"),
        _entry(20, "error: slow query"),
    ]
    lines = _source(entries, requests).fetch({"orders", "orders-db"}, START, END)

    assert [line.message for line in lines] == [
        "warning: deploy started",
        "error: slow query",
        "error: connection pool exhausted",
    ]
    assert len(requests) == 1
    params = requests[0].url.params
    assert params["query"].startswith("{service_name=~`orders|orders\\-db`} |~ `")
    assert params["direction"] == "forward"
    assert int(params["start"]) == BASE
    assert int(params["end"]) == int(END.timestamp()) * 1_000_000_000 + 1000  # inclusive end


def test_maps_json_fields_onto_log_line() -> None:
    payload = '{"level":"error","message":"boom","trace_id":"abc","extra":1}'
    lines = _source([_entry(1, payload)], []).fetch({"orders"}, START, END)

    assert len(lines) == 1
    line = lines[0]
    assert line.service == "orders"
    assert line.level == "ERROR"
    assert line.message == "boom"
    assert line.trace_id == "abc"
    assert line.attributes == {"extra": 1}
    assert line.id.startswith("loki-")


def test_plain_text_keeps_raw_message_and_defaults_level() -> None:
    lines = _source([_entry(1, "error: all quiet")], []).fetch({"orders"}, START, END)

    assert lines[0].message == "error: all quiet"
    assert lines[0].level == "INFO"  # no structured level field; body still matched LogQL
    assert lines[0].trace_id is None


def test_no_services_makes_no_request() -> None:
    requests: list[httpx.Request] = []
    assert _source([], requests).fetch(set(), START, END) == []
    assert requests == []
