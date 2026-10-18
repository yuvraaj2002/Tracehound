from datetime import UTC, datetime
from pathlib import Path

from tracehound.tools.logs import LogReader

SCENARIO = Path(__file__).resolve().parents[2] / "scenarios" / "checkout_db_pool_exhaustion"


def test_fetch_filters_by_service_and_window_oldest_first() -> None:
    start = datetime(2026, 10, 15, 13, 45, tzinfo=UTC)
    end = datetime(2026, 10, 15, 14, 30, tzinfo=UTC)
    services = {"checkout-api"}
    lines = LogReader(SCENARIO).fetch(services, start, end)

    print(f"\nQUERY: services={sorted(services)} start={start} end={end}")
    print(f"RESULT: {len(lines)} lines")
    for line in lines:
        print(f"  {line.id}  {line.timestamp:%H:%M:%S}  {line.level:<5}  {line.message}")

    assert lines
    assert {line.service for line in lines} == {"checkout-api"}
    assert all(start <= line.timestamp <= end for line in lines)
    assert [line.timestamp for line in lines] == sorted(line.timestamp for line in lines)


if __name__ == "__main__":
    test_fetch_filters_by_service_and_window_oldest_first()
