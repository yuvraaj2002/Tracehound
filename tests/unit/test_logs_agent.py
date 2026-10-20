from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import BaseModel

from tracehound.agents.logs import LogsAgent, LogsAnswer
from tracehound.agents.logs.agent import CitedClaim
from tracehound.schemas import InvestigationScope, Specialist, SpecialistTask, hash_payload
from tracehound.tools.logs import LogReader

SCENARIO = Path(__file__).resolve().parents[2] / "scenarios" / "checkout_db_pool_exhaustion"
SERVICES = ["checkout-api", "orders-db"]


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
        symptom_window_end=datetime(2026, 10, 15, 14, 30, tzinfo=UTC),
        change_window_start=datetime(2026, 10, 15, 12, 45, tzinfo=UTC),
        tasks=[
            SpecialistTask(specialist=s, question=f"{s} question", services=SERVICES)
            for s in Specialist
        ],
        rationale="test",
    )


def _answer(*log_ids: str) -> LogsAnswer:
    return LogsAnswer(
        summary="From 13:55 checkout-api logs pool timeouts.",
        findings=[CitedClaim(claim="Pool timeouts start at 13:55", log_ids=list(log_ids))],
    )


def test_context_has_logs_question_and_only_scoped_services(scope: InvestigationScope) -> None:
    llm = FakeLLM(_answer("log-008"))
    LogsAgent(SCENARIO, llm)(scope, uuid4())

    user = llm.calls[0]["user"]
    assert user.startswith("<context>\n") and user.endswith("\n</context>")
    assert "logs question" in user and "log-008" in user
    assert "payments-api" not in user


def test_citations_become_evidence(scope: InvestigationScope) -> None:
    run_id = uuid4()
    report = LogsAgent(SCENARIO, FakeLLM(_answer("log-006", "log-008", "log-006")))(scope, run_id)

    assert report.findings[0].evidence_ids == ["log-006", "log-008", "log-006"]
    assert [e.id for e in report.evidence] == ["log-006", "log-008"]
    lines = LogReader(SCENARIO).fetch(
        set(SERVICES), scope.change_window_start, scope.symptom_window_end
    )
    raw = next(line for line in lines if line.id == "log-008")
    evidence = report.evidence[1]
    assert evidence.run_id == run_id
    assert evidence.event_time == datetime(2026, 10, 15, 13, 55, 14, tzinfo=UTC)
    assert evidence.source_locator == "logs.json#log-008"
    assert "QueuePool" in evidence.excerpt
    assert evidence.payload_hash == hash_payload(raw.model_dump(mode="json"))


@pytest.mark.parametrize("log_id", ["log-999", "log-001"])  # made up / payments-api, not shown
def test_citing_unseen_line_raises(scope: InvestigationScope, log_id: str) -> None:
    with pytest.raises(ValueError, match="not shown"):
        LogsAgent(SCENARIO, FakeLLM(_answer("log-008", log_id)))(scope, uuid4())


def test_context_uses_the_logs_task_services_not_the_whole_scope(
    scope: InvestigationScope,
) -> None:
    wide = ["checkout-api", "orders-db", "payments-api"]
    tasks = [t.model_copy(update={"services": wide}) for t in scope.tasks]
    tasks = [
        t.model_copy(update={"services": ["checkout-api"]}) if t.specialist == "logs" else t
        for t in tasks
    ]
    scope = scope.model_copy(update={"services": wide, "tasks": tasks})

    ctx = LogsAgent(SCENARIO, FakeLLM(_answer("log-008"))).build_context(scope)
    assert ctx.services == ["checkout-api"]
    assert {line.service for line in ctx.logs} == {"checkout-api"}
