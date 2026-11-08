from datetime import UTC, datetime, timedelta

from tracehound.schemas.logs import LogLine
from tracehound.tools.logs import dedupe_by_message

START = datetime(2026, 10, 15, 13, 45, tzinfo=UTC)


def _line(
    second: int,
    message: str,
    *,
    line_id: str | None = None,
    service: str = "orders",
    level: str = "ERROR",
) -> LogLine:
    return LogLine(
        id=line_id or f"log-{second}",
        timestamp=START + timedelta(seconds=second),
        service=service,
        level=level,  # type: ignore[arg-type]
        message=message,
        trace_id=None,
    )


def test_same_message_collapses_with_occurrence() -> None:
    lines = [
        _line(1, "pool exhausted", line_id="a"),
        _line(2, "pool exhausted", line_id="b"),
        _line(3, "pool exhausted", line_id="c"),
    ]

    out = dedupe_by_message(lines)

    assert len(out) == 1
    assert out[0].id == "a"
    assert out[0].timestamp == START + timedelta(seconds=1)
    assert out[0].occurrence == 3


def test_different_messages_stay_separate() -> None:
    lines = [_line(1, "warning: slow"), _line(2, "error: timeout")]

    out = dedupe_by_message(lines)

    assert [line.message for line in out] == ["warning: slow", "error: timeout"]
    assert all(line.occurrence == 1 for line in out)


def test_preserves_first_seen_order_across_interleaved_duplicates() -> None:
    lines = [
        _line(1, "alpha"),
        _line(2, "beta"),
        _line(3, "alpha"),
        _line(4, "beta"),
    ]

    out = dedupe_by_message(lines)

    assert [(line.message, line.occurrence) for line in out] == [("alpha", 2), ("beta", 2)]
