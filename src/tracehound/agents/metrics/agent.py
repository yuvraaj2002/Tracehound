"""Metrics agent: reads the in-scope series and turns the model's citations into Evidence."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tracehound.agents.inference import StructuredLLM
from tracehound.agents.metrics.prompt import SYSTEM_PROMPT
from tracehound.schemas.evidence import Evidence, EvidenceSource, hash_payload
from tracehound.schemas.finding import Finding, SpecialistReport
from tracehound.schemas.telemetry import MetricSeries
from tracehound.schemas.triage import InvestigationScope, Specialist
from tracehound.tools.metrics import MetricReader


class MetricsContext(BaseModel):
    """Everything the model is shown, gathered by code before the call."""

    question: str
    services: list[str]
    window_start: datetime
    window_end: datetime
    series: list[MetricSeries]


class CitedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    series_ids: list[str] = Field(min_length=1, description="IDs of the series that show it")


class MetricsAnswer(BaseModel):
    """What the model decides. Cited IDs are checked against the context after."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    findings: list[CitedClaim]


class MetricsAgent:
    """Deterministic metric fetch, then one LLM call. Errors propagate to the caller."""

    def __init__(self, scenario_dir: Path, llm: StructuredLLM) -> None:
        self._reader = MetricReader(scenario_dir)
        self._llm = llm

    def __call__(self, scope: InvestigationScope, run_id: UUID) -> SpecialistReport:
        ctx = self.build_context(scope)
        # Escaping <> keeps the JSON valid but stops untrusted text from closing the tag.
        data = ctx.model_dump_json(indent=2).replace("<", "\\u003c").replace(">", "\\u003e")
        answer = self._llm.generate(
            system=SYSTEM_PROMPT, user=f"<context>\n{data}\n</context>", schema=MetricsAnswer
        )
        return self.report_from_answer(ctx, answer, run_id)

    def build_context(self, scope: InvestigationScope) -> MetricsContext:
        task = scope.task_for(Specialist.METRICS)
        return MetricsContext(
            question=task.question,
            services=task.services,
            window_start=scope.change_window_start,
            window_end=scope.symptom_window_end,
            series=self._reader.fetch(
                set(task.services), scope.change_window_start, scope.symptom_window_end
            ),
        )

    @staticmethod
    def report_from_answer(
        ctx: MetricsContext, answer: MetricsAnswer, run_id: UUID
    ) -> SpecialistReport:
        """Build evidence from the series the model cited. Raises ValueError on unseen IDs."""
        shown = {series.id: series for series in ctx.series}
        cited = [series_id for claim in answer.findings for series_id in claim.series_ids]
        unknown = set(cited) - shown.keys()
        if unknown:
            raise ValueError(f"model cited series it was not shown: {sorted(unknown)}")
        collected_at = datetime.now(UTC)
        return SpecialistReport(
            specialist=Specialist.METRICS,
            summary=answer.summary,
            findings=[
                Finding(specialist=Specialist.METRICS, claim=c.claim, evidence_ids=c.series_ids)
                for c in answer.findings
            ],
            evidence=[
                _evidence(shown[series_id], run_id, collected_at)
                for series_id in dict.fromkeys(cited)
            ],
        )


def _evidence(series: MetricSeries, run_id: UUID, collected_at: datetime) -> Evidence:
    """One record per cited series, covering the points the model was shown."""
    first, last = series.points[0], series.points[-1]
    low = min(p.value for p in series.points)
    high = max(p.value for p in series.points)
    return Evidence(
        id=series.id,
        run_id=run_id,
        source_type=EvidenceSource.METRIC,
        source_locator=f"metrics.json#{series.id}",
        service=series.service,
        event_time=first.timestamp,
        collected_at=collected_at,
        payload_hash=hash_payload(series.model_dump(mode="json")),
        excerpt=(
            f"{series.name} ({series.unit}) {first.timestamp:%H:%M}-{last.timestamp:%H:%M}: "
            f"first {first.value:g}, last {last.value:g}, min {low:g}, max {high:g}"
        ),
        metadata={
            "name": series.name,
            "unit": series.unit,
            "window_end": last.timestamp.isoformat(),
        },
    )
