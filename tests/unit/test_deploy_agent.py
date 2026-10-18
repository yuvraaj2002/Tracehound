from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import BaseModel

from tracehound.agents.deploy import DeployAgent, DeployAnswer
from tracehound.schemas import InvestigationScope, Specialist, SpecialistTask, hash_payload
from tracehound.tools.deploys import DeployReader

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


def _answer(*deploy_ids: str) -> DeployAnswer:
    return DeployAnswer.model_validate(
        {
            "summary": "checkout-api deployed 1.14.0 at 13:52.",
            "findings": [
                {"claim": "DB_POOL_SIZE cut from 20 to 5", "deploy_ids": list(deploy_ids)}
            ],
        }
    )


def test_fetch_filters_services_and_window_sorted() -> None:
    both = DeployReader(SCENARIO).fetch({"checkout-api", "payments-api"}, START, END)
    assert [d.id for d in both] == ["dep-001", "dep-002"]
    assert [d.id for d in DeployReader(SCENARIO).fetch({"checkout-api"}, START, END)] == ["dep-002"]
    assert DeployReader(SCENARIO).fetch({"checkout-api"}, START, START) == []


def test_context_has_deploy_question_and_only_scoped_services(
    scope: InvestigationScope,
) -> None:
    llm = FakeLLM(_answer("dep-002"))
    DeployAgent(SCENARIO, llm)(scope, uuid4())

    user = llm.calls[0]["user"]
    assert user.startswith("<context>\n") and user.endswith("\n</context>")
    assert "deploy question" in user and "dep-002" in user
    assert "dep-001" not in user  # payments-api is out of scope


def test_citations_become_evidence(scope: InvestigationScope) -> None:
    run_id = uuid4()
    report = DeployAgent(SCENARIO, FakeLLM(_answer("dep-002", "dep-002")))(scope, run_id)

    assert report.specialist is Specialist.DEPLOY
    assert [e.id for e in report.evidence] == ["dep-002"]
    raw = DeployReader(SCENARIO).fetch({"checkout-api"}, START, END)[0]
    evidence = report.evidence[0]
    assert evidence.run_id == run_id
    assert evidence.event_time == raw.deployed_at
    assert evidence.source_locator == "deploys.json#dep-002"
    assert evidence.excerpt.startswith("checkout-api 1.13.4->1.14.0: ")
    assert "DB_POOL_SIZE 20->5" in evidence.excerpt
    assert evidence.payload_hash == hash_payload(raw.model_dump(mode="json"))


@pytest.mark.parametrize("deploy_id", ["dep-999", "dep-001"])  # made up / payments-api
def test_citing_unseen_deploy_raises(scope: InvestigationScope, deploy_id: str) -> None:
    with pytest.raises(ValueError, match="not shown"):
        DeployAgent(SCENARIO, FakeLLM(_answer("dep-002", deploy_id)))(scope, uuid4())
