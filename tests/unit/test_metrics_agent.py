from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import BaseModel

from tracehound.agents.metrics import MetricsAgent, MetricsAnswer
from tracehound.schemas import InvestigationScope, Specialist, SpecialistTask, hash_payload
from tracehound.tools.metrics import FileMetricSource

SCENARIO = Path(__file__).resolve().parents[2] / "scenarios" / "checkout_db_pool_exhaustion"
SERVICES = ["checkout-api", "orders-db"]
START = datetime(2026, 10, 15, 12, 45, tzinfo=UTC)
END = datetime(2026, 10, 15, 14, 30, tzinfo=UTC)


class FakeLLM:
    def __init__(self, result: BaseModel) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def generate(self, *, system: str, user: str, schema: type[BaseModel]) -> Any:
        self.calls.append({"system": system, "user": user, "schema": schema})
        return self.result


@pytest.fixture
def scope() -> InvestigationScope:
    return InvestigationScope(
        alert_service="checkout-api",
        services=SERVICES,
        symptom_window_start=datetime(2026, 10, 15, 13, 45, tzinfo=UTC),
        symptom_window_end=END,
        change_window_start=START,
        tasks=[
            SpecialistTask(specialist=s, question=f"{s} question", services=SERVICES)
            for s in Specialist
        ],
        rationale="test",
    )


def _answer(*series_ids: str) -> MetricsAnswer:
    return MetricsAnswer.model_validate(
        {
            "summary": "Latency jumps at 13:55.",
            "findings": [{"claim": "p95 rose to ~2000 ms", "series_ids": list(series_ids)}],
        }
    )


def test_fetch_filters_services_and_trims_points_to_window() -> None:
    start = datetime(2026, 10, 15, 14, 0, tzinfo=UTC)
    series = FileMetricSource(SCENARIO).fetch({"orders-db"}, start, END)

    assert {s.id for s in series} == {"met-006", "met-007"}
    assert all(start <= p.timestamp <= END for s in series for p in s.points)
    assert FileMetricSource(SCENARIO).fetch({"checkout-api"}, START, START) == []


def test_context_has_metrics_question_and_only_scoped_services(
    scope: InvestigationScope,
) -> None:
    llm = FakeLLM(_answer("met-002"))
    MetricsAgent(FileMetricSource(SCENARIO), llm)(scope, uuid4())

    user = llm.calls[0]["user"]
    assert user.startswith("<context>\n") and user.endswith("\n</context>")
    assert "metrics question" in user and "met-002" in user
    assert "met-008" not in user  # payments-api is out of scope


def test_citations_become_evidence(scope: InvestigationScope) -> None:
    run_id = uuid4()
    report = MetricsAgent(
        FileMetricSource(SCENARIO), FakeLLM(_answer("met-002", "met-005", "met-002"))
    )(scope, run_id)

    assert report.specialist is Specialist.METRICS
    assert [e.id for e in report.evidence] == ["met-002", "met-005"]
    raw = next(
        s for s in FileMetricSource(SCENARIO).fetch(set(SERVICES), START, END) if s.id == "met-002"
    )
    evidence = report.evidence[0]
    assert evidence.run_id == run_id
    assert evidence.event_time == raw.points[0].timestamp
    assert evidence.source_locator == "metrics.json#met-002"
    assert evidence.excerpt.startswith("http_p95_latency_ms (ms) 13:45-14:30")
    assert evidence.payload_hash == hash_payload(raw.model_dump(mode="json"))


@pytest.mark.parametrize("series_id", ["met-999", "met-008"])  # made up / payments-api
def test_citing_unseen_series_raises(scope: InvestigationScope, series_id: str) -> None:
    with pytest.raises(ValueError, match="not shown"):
        MetricsAgent(FileMetricSource(SCENARIO), FakeLLM(_answer("met-002", series_id)))(
            scope, uuid4()
        )
