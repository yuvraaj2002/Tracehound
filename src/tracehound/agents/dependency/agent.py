"""Dependency agent: reads in-scope spans and edges, turns citations into Evidence."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tracehound.agents.dependency.prompt import SYSTEM_PROMPT
from tracehound.agents.inference import StructuredLLM
from tracehound.schemas.evidence import Evidence, EvidenceSource, hash_payload
from tracehound.schemas.finding import Finding, SpecialistReport
from tracehound.schemas.telemetry import Edge, Span
from tracehound.schemas.triage import InvestigationScope, Specialist
from tracehound.tools.traces import TraceReader
from tracehound.tools.triage import load_topology


class DependencyContext(BaseModel):
    """Everything the model is shown, gathered by code before the call."""

    question: str
    services: list[str]
    window_start: datetime
    window_end: datetime
    edges: list[Edge]
    spans: list[Span]


class CitedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    span_ids: list[str] = Field(min_length=1, description="IDs of the spans that show it")


class DependencyAnswer(BaseModel):
    """What the model decides. Cited IDs are checked against the context after."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    findings: list[CitedClaim]


class DependencyAgent:
    """Deterministic trace and topology fetch, then one LLM call. Errors propagate."""

    def __init__(self, scenario_dir: Path, llm: StructuredLLM) -> None:
        self._reader = TraceReader(scenario_dir)
        self._topology = load_topology(scenario_dir)
        self._llm = llm

    def __call__(self, scope: InvestigationScope, run_id: UUID) -> SpecialistReport:
        ctx = self.build_context(scope)
        # Escaping <> keeps the JSON valid but stops untrusted text from closing the tag.
        data = ctx.model_dump_json(indent=2).replace("<", "\\u003c").replace(">", "\\u003e")
        answer = self._llm.generate(
            system=SYSTEM_PROMPT, user=f"<context>\n{data}\n</context>", schema=DependencyAnswer
        )
        return self.report_from_answer(ctx, answer, run_id)

    def build_context(self, scope: InvestigationScope) -> DependencyContext:
        services = set(scope.services)
        return DependencyContext(
            question=scope.task_for(Specialist.DEPENDENCY).question,
            services=scope.services,
            window_start=scope.change_window_start,
            window_end=scope.symptom_window_end,
            edges=self._topology.edges_touching(services),
            spans=self._reader.fetch(services, scope.change_window_start, scope.symptom_window_end),
        )

    @staticmethod
    def report_from_answer(
        ctx: DependencyContext, answer: DependencyAnswer, run_id: UUID
    ) -> SpecialistReport:
        """Build evidence from the spans the model cited. Raises ValueError on unseen IDs."""
        shown = {span.id: span for span in ctx.spans}
        cited = [span_id for claim in answer.findings for span_id in claim.span_ids]
        unknown = set(cited) - shown.keys()
        if unknown:
            raise ValueError(f"model cited spans it was not shown: {sorted(unknown)}")
        collected_at = datetime.now(UTC)
        return SpecialistReport(
            specialist=Specialist.DEPENDENCY,
            summary=answer.summary,
            findings=[
                Finding(specialist=Specialist.DEPENDENCY, claim=c.claim, evidence_ids=c.span_ids)
                for c in answer.findings
            ],
            evidence=[
                _evidence(shown[span_id], run_id, collected_at) for span_id in dict.fromkeys(cited)
            ],
        )


def _evidence(span: Span, run_id: UUID, collected_at: datetime) -> Evidence:
    """One record per cited span."""
    return Evidence(
        id=span.id,
        run_id=run_id,
        source_type=EvidenceSource.TRACE,
        source_locator=f"traces.json#{span.id}",
        service=span.service,
        event_time=span.start,
        collected_at=collected_at,
        payload_hash=hash_payload(span.model_dump(mode="json")),
        excerpt=(
            f"{span.service} {span.name} {span.duration_ms:g}ms {span.status} "
            f"(trace {span.trace_id[:4]}…)"
        ),
        metadata={"trace_id": span.trace_id, "parent_span_id": span.parent_span_id},
    )
