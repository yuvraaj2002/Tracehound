"""Hypothesis agent: one LLM call over every finding, checked and turned into Hypothesis records."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tracehound.agents.hypothesis.prompt import SYSTEM_PROMPT
from tracehound.agents.inference import StructuredLLM
from tracehound.schemas.evidence import Evidence, EvidenceId, EvidenceSource
from tracehound.schemas.finding import Finding
from tracehound.schemas.hypothesis import (
    ConfidenceBand,
    Hypothesis,
    HypothesisStatus,
    VerificationStep,
)
from tracehound.schemas.incident import IncidentRecord
from tracehound.schemas.triage import Specialist


class EvidenceView(BaseModel):
    """The parts of an Evidence record the model needs; hashes and locators stay with code."""

    id: EvidenceId
    source: EvidenceSource
    service: str
    time: datetime
    excerpt: str


class HypothesisContext(BaseModel):
    """Everything the model is shown, gathered by code before the call."""

    service: str
    symptom: str
    symptom_window_start: datetime
    symptom_window_end: datetime
    findings: list[Finding]
    evidence: list[EvidenceView]


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str
    mechanism: str
    supporting_evidence_ids: list[str]
    contradicting_evidence_ids: list[str]
    status: Literal["supported", "inconclusive", "refuted"]
    confidence: ConfidenceBand
    confidence_rationale: str
    verification_steps: list[VerificationStep]


class HypothesisAnswer(BaseModel):
    """What the model decides. Cited IDs are checked against the context after."""

    model_config = ConfigDict(extra="forbid")

    hypotheses: list[Draft] = Field(min_length=1, max_length=3)


class HypothesisAgent:
    """One LLM call over all specialist results. Errors propagate to the caller."""

    def __init__(self, llm: StructuredLLM) -> None:
        self._llm = llm

    def __call__(
        self,
        incident: IncidentRecord,
        findings: list[Finding],
        evidence: dict[EvidenceId, Evidence],
    ) -> list[Hypothesis]:
        ctx = self.build_context(incident, findings, evidence)
        # Escaping <> keeps the JSON valid but stops untrusted text from closing the tag.
        data = ctx.model_dump_json(indent=2).replace("<", "\\u003c").replace(">", "\\u003e")
        answer = self._llm.generate(
            system=SYSTEM_PROMPT, user=f"<context>\n{data}\n</context>", schema=HypothesisAnswer
        )
        return self.hypotheses_from_answer(ctx, answer, incident.run_id)

    @staticmethod
    def build_context(
        incident: IncidentRecord,
        findings: list[Finding],
        evidence: dict[EvidenceId, Evidence],
    ) -> HypothesisContext:
        order = list(Specialist)
        return HypothesisContext(
            service=incident.service_id,
            symptom=incident.symptom,
            symptom_window_start=incident.window_start,
            symptom_window_end=incident.window_end,
            findings=sorted(findings, key=lambda f: order.index(f.specialist)),
            evidence=[
                EvidenceView(
                    id=e.id,
                    source=e.source_type,
                    service=e.service,
                    time=e.event_time,
                    excerpt=e.excerpt,
                )
                for e in sorted(evidence.values(), key=lambda e: (e.event_time, e.id))
            ],
        )

    @staticmethod
    def hypotheses_from_answer(
        ctx: HypothesisContext, answer: HypothesisAnswer, run_id: UUID
    ) -> list[Hypothesis]:
        """Raises ValueError on unseen IDs, or when a draft breaks the Hypothesis rules."""
        shown = {e.id for e in ctx.evidence}
        cited = {
            evidence_id
            for draft in answer.hypotheses
            for evidence_id in (*draft.supporting_evidence_ids, *draft.contradicting_evidence_ids)
        }
        unknown = cited - shown
        if unknown:
            raise ValueError(f"model cited evidence it was not shown: {sorted(unknown)}")
        return [
            Hypothesis(
                run_id=run_id,
                statement=draft.statement,
                mechanism=draft.mechanism,
                confidence=draft.confidence,
                confidence_rationale=draft.confidence_rationale,
                status=HypothesisStatus(draft.status),
                supporting_evidence_ids=list(dict.fromkeys(draft.supporting_evidence_ids)),
                contradicting_evidence_ids=list(dict.fromkeys(draft.contradicting_evidence_ids)),
                verification_steps=draft.verification_steps,
            )
            for draft in answer.hypotheses
        ]
