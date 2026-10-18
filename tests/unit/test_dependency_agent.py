from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import BaseModel

from tracehound.agents.dependency import DependencyAgent, DependencyAnswer
from tracehound.schemas import InvestigationScope, Specialist, SpecialistTask, hash_payload
from tracehound.tools.traces import TraceReader

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


def _answer(*span_ids: str) -> DependencyAnswer:
    return DependencyAnswer.model_validate(
        {
            "summary": "Time goes to db.pool.acquire.",
            "findings": [{"claim": "pool acquire took 2003 ms", "span_ids": list(span_ids)}],
        }
    )


def test_fetch_filters_services_and_window_sorted() -> None:
    reader = TraceReader(SCENARIO)
    spans = reader.fetch({"checkout-api"}, START, END)

    assert [s.id for s in spans] == ["trc-001", "trc-002", "trc-004", "trc-005"]
    assert spans[0].start.tzinfo is UTC
    late = reader.fetch({"checkout-api"}, datetime(2026, 10, 15, 14, 0, tzinfo=UTC), END)
    assert [s.id for s in late] == ["trc-004", "trc-005"]
    assert reader.fetch({"payments-api"}, START, END)[0].id == "trc-003"


def test_context_has_question_edges_and_only_scoped_spans(scope: InvestigationScope) -> None:
    llm = FakeLLM(_answer("trc-005"))
    DependencyAgent(SCENARIO, llm)(scope, uuid4())

    user = llm.calls[0]["user"]
    assert user.startswith("<context>\n") and user.endswith("\n</context>")
    assert "dependency question" in user and "trc-005" in user
    assert "trc-003" not in user  # payments-api is out of scope
    assert '"target": "orders-db"' in user
    assert "<" not in user[len("<context>") : -len("</context>")]


def test_citations_become_evidence(scope: InvestigationScope) -> None:
    run_id = uuid4()
    report = DependencyAgent(SCENARIO, FakeLLM(_answer("trc-005", "trc-004", "trc-005")))(
        scope, run_id
    )

    assert report.specialist is Specialist.DEPENDENCY
    assert [e.id for e in report.evidence] == ["trc-005", "trc-004"]
    raw = next(
        s for s in TraceReader(SCENARIO).fetch(set(SERVICES), START, END) if s.id == "trc-005"
    )
    evidence = report.evidence[0]
    assert evidence.run_id == run_id
    assert evidence.event_time == raw.start
    assert evidence.source_locator == "traces.json#trc-005"
    assert evidence.excerpt == "checkout-api db.pool.acquire 2003ms error (trace 4bf9…)"
    assert evidence.payload_hash == hash_payload(raw.model_dump(mode="json"))
    assert evidence.metadata["parent_span_id"] == raw.parent_span_id


@pytest.mark.parametrize("span_id", ["trc-999", "trc-003"])  # made up / payments-api
def test_citing_unseen_span_raises(scope: InvestigationScope, span_id: str) -> None:
    with pytest.raises(ValueError, match="not shown"):
        DependencyAgent(SCENARIO, FakeLLM(_answer("trc-005", span_id)))(scope, uuid4())
