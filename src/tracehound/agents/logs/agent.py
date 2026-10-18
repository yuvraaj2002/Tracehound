"""Logs agent: reads the in-scope log lines and turns the model's citations into Evidence."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tracehound.agents.inference import StructuredLLM
from tracehound.agents.logs.prompt import SYSTEM_PROMPT
from tracehound.schemas.evidence import Evidence, EvidenceSource, hash_payload
from tracehound.schemas.finding import Finding, SpecialistReport
from tracehound.schemas.telemetry import LogLine
from tracehound.schemas.triage import InvestigationScope, Specialist
from tracehound.tools.logs import LogReader


class LogsContext(BaseModel):
    """Everything the model is shown, gathered by code before the call."""

    question: str
    services: list[str]
    window_start: datetime
    window_end: datetime
    logs: list[LogLine]


class CitedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    log_ids: list[str] = Field(min_length=1, description="IDs of the log lines that show it")


class LogsAnswer(BaseModel):
    """What the model decides. Cited IDs are checked against the context after."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    findings: list[CitedClaim]


class LogsAgent:
    """Deterministic log fetch, then one LLM call. Errors propagate to the caller."""

    def __init__(self, scenario_dir: Path, llm: StructuredLLM) -> None:
        self._reader = LogReader(scenario_dir)
        self._llm = llm

    def __call__(self, scope: InvestigationScope, run_id: UUID) -> SpecialistReport:
        ctx = self.build_context(scope)
        # Escaping <> keeps the JSON valid but stops untrusted text from closing the tag.
        data = ctx.model_dump_json(indent=2).replace("<", "\\u003c").replace(">", "\\u003e")
        answer = self._llm.generate(
            system=SYSTEM_PROMPT, user=f"<context>\n{data}\n</context>", schema=LogsAnswer
        )
        return self.report_from_answer(ctx, answer, run_id)

    def build_context(self, scope: InvestigationScope) -> LogsContext:
        return LogsContext(
            question=scope.task_for(Specialist.LOGS).question,
            services=scope.services,
            window_start=scope.change_window_start,
            window_end=scope.symptom_window_end,
            logs=self._reader.fetch(
                set(scope.services), scope.change_window_start, scope.symptom_window_end
            ),
        )

    @staticmethod
    def report_from_answer(ctx: LogsContext, answer: LogsAnswer, run_id: UUID) -> SpecialistReport:
        """Build evidence from the lines the model cited. Raises ValueError on unseen IDs."""
        shown = {line.id: line for line in ctx.logs}
        cited = [log_id for claim in answer.findings for log_id in claim.log_ids]
        unknown = set(cited) - shown.keys()
        if unknown:
            raise ValueError(f"model cited log lines it was not shown: {sorted(unknown)}")
        collected_at = datetime.now(UTC)
        return SpecialistReport(
            specialist=Specialist.LOGS,
            summary=answer.summary,
            findings=[
                Finding(specialist=Specialist.LOGS, claim=c.claim, evidence_ids=c.log_ids)
                for c in answer.findings
            ],
            evidence=[
                _evidence(shown[log_id], run_id, collected_at) for log_id in dict.fromkeys(cited)
            ],
        )


def _evidence(line: LogLine, run_id: UUID, collected_at: datetime) -> Evidence:
    return Evidence(
        id=line.id,
        run_id=run_id,
        source_type=EvidenceSource.LOG,
        source_locator=f"logs.json#{line.id}",
        service=line.service,
        event_time=line.timestamp,
        collected_at=collected_at,
        payload_hash=hash_payload(line.model_dump(mode="json")),
        excerpt=line.message[:2000],
        metadata={"level": line.level, "trace_id": line.trace_id},
    )
