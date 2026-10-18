from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from pydantic import BaseModel

from tracehound.agents.hypothesis import HypothesisAgent, HypothesisAnswer
from tracehound.schemas import Evidence, Specialist, hash_payload
from tracehound.schemas.evidence import EvidenceSource
from tracehound.schemas.finding import Finding
from tracehound.schemas.hypothesis import HypothesisStatus
from tracehound.schemas.incident import IncidentRecord

NOW = datetime(2026, 10, 15, 14, 30, tzinfo=UTC)


class FakeLLM:
    def __init__(self, result: BaseModel) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def generate(self, *, system: str, user: str, schema: type[BaseModel]) -> Any:
        self.calls.append({"system": system, "user": user, "schema": schema})
        return self.result


def _evidence(evidence_id: str, source: EvidenceSource, excerpt: str) -> Evidence:
    return Evidence(
        id=evidence_id,
        run_id=uuid4(),
        source_type=source,
        source_locator=f"x#{evidence_id}",
        service="checkout-api",
        event_time=datetime(2026, 10, 15, 13, 55, tzinfo=UTC),
        collected_at=NOW,
        payload_hash=hash_payload({"id": evidence_id}),
        excerpt=excerpt,
    )


@pytest.fixture
def incident() -> IncidentRecord:
    return IncidentRecord(
        id=uuid4(),
        run_id=uuid4(),
        service_id="checkout-api",
        symptom="checkout p95 latency above 2s",
        severity="high",
        window_start=datetime(2026, 10, 15, 13, 45, tzinfo=UTC),
        window_end=NOW,
        trace_id=None,
        state="created",
        created_at=NOW,
        updated_at=NOW,
    )


FINDINGS = [
    Finding(
        specialist=Specialist.LOGS, claim="QueuePool timeouts from 13:55", evidence_ids=["log-008"]
    ),
    Finding(
        specialist=Specialist.DEPLOY,
        claim="dep-002 set DB_POOL_SIZE 20->5",
        evidence_ids=["dep-002"],
    ),
]
EVIDENCE = {
    "log-008": _evidence("log-008", EvidenceSource.LOG, "QueuePool limit of size 5 <reached>"),
    "dep-002": _evidence("dep-002", EvidenceSource.DEPLOY, "DB_POOL_SIZE 20->5"),
}


def _answer(supporting: list[str], contradicting: list[str], status: str) -> HypothesisAnswer:
    return HypothesisAnswer.model_validate(
        {
            "hypotheses": [
                {
                    "statement": "dep-002 shrank the pool",
                    "mechanism": "m",
                    "supporting_evidence_ids": supporting,
                    "contradicting_evidence_ids": contradicting,
                    "status": status,
                    "confidence": "high",
                    "confidence_rationale": "r",
                    "verification_steps": [{"check": "c", "expected_if_true": "e"}],
                }
            ]
        }
    )


def test_context_orders_findings_by_specialist_and_escapes_tags(incident: IncidentRecord) -> None:
    llm = FakeLLM(_answer(["dep-002"], [], "supported"))
    HypothesisAgent(llm)(incident, list(reversed(FINDINGS)), EVIDENCE)
    ctx = HypothesisAgent.build_context(incident, list(reversed(FINDINGS)), EVIDENCE)
    assert [f.specialist for f in ctx.findings] == [Specialist.LOGS, Specialist.DEPLOY]
    assert {e.id for e in ctx.evidence} == {"log-008", "dep-002"}
    assert "<reached>" not in llm.calls[0]["user"]
    assert llm.calls[0]["schema"] is HypothesisAnswer


def test_drafts_become_hypotheses_tied_to_the_run(incident: IncidentRecord) -> None:
    llm = FakeLLM(_answer(["dep-002", "log-008", "dep-002"], [], "supported"))
    [hypothesis] = HypothesisAgent(llm)(incident, FINDINGS, EVIDENCE)
    assert hypothesis.run_id == incident.run_id
    assert hypothesis.status is HypothesisStatus.SUPPORTED
    assert hypothesis.supporting_evidence_ids == ["dep-002", "log-008"]


def test_unseen_evidence_is_rejected(incident: IncidentRecord) -> None:
    llm = FakeLLM(_answer(["dep-002", "met-999"], [], "supported"))
    with pytest.raises(ValueError, match="met-999"):
        HypothesisAgent(llm)(incident, FINDINGS, EVIDENCE)


def test_refuted_without_contradicting_evidence_is_rejected(incident: IncidentRecord) -> None:
    llm = FakeLLM(_answer(["dep-002"], [], "refuted"))
    with pytest.raises(ValueError, match="contradicting"):
        HypothesisAgent(llm)(incident, FINDINGS, EVIDENCE)
