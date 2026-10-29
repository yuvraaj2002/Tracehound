"""Deploy agent: reads the in-scope deploys and turns the model's citations into Evidence."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tracehound.agents.deploy.prompt import SYSTEM_PROMPT
from tracehound.agents.inference import StructuredLLM
from tracehound.schemas.evidence import Evidence, EvidenceSource, hash_payload
from tracehound.schemas.finding import Finding, SpecialistReport
from tracehound.schemas.telemetry import Deploy
from tracehound.schemas.triage import InvestigationScope, Specialist
from tracehound.tools.deploys import DeploySource


class DeployContext(BaseModel):
    """Everything the model is shown, gathered by code before the call."""

    question: str
    services: list[str]
    window_start: datetime
    window_end: datetime
    deploys: list[Deploy]


class CitedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    deploy_ids: list[str] = Field(min_length=1, description="IDs of the deploys that show it")


class DeployAnswer(BaseModel):
    """What the model decides. Cited IDs are checked against the context after."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    findings: list[CitedClaim]


class DeployAgent:
    """Deterministic deploy fetch from any ``DeploySource``, then one LLM call. Errors propagate."""

    def __init__(self, source: DeploySource, llm: StructuredLLM) -> None:
        self._source = source
        self._llm = llm

    def __call__(self, scope: InvestigationScope, run_id: UUID) -> SpecialistReport:
        ctx = self.build_context(scope)
        # Escaping <> keeps the JSON valid but stops untrusted text from closing the tag.
        data = ctx.model_dump_json(indent=2).replace("<", "\\u003c").replace(">", "\\u003e")
        answer = self._llm.generate(
            system=SYSTEM_PROMPT, user=f"<context>\n{data}\n</context>", schema=DeployAnswer
        )
        return self.report_from_answer(ctx, answer, run_id)

    def build_context(self, scope: InvestigationScope) -> DeployContext:
        task = scope.task_for(Specialist.DEPLOY)
        return DeployContext(
            question=task.question,
            services=task.services,
            window_start=scope.change_window_start,
            window_end=scope.symptom_window_end,
            deploys=self._source.fetch(
                set(task.services), scope.change_window_start, scope.symptom_window_end
            ),
        )

    @staticmethod
    def report_from_answer(
        ctx: DeployContext, answer: DeployAnswer, run_id: UUID
    ) -> SpecialistReport:
        """Build evidence from the deploys the model cited. Raises ValueError on unseen IDs."""
        shown = {deploy.id: deploy for deploy in ctx.deploys}
        cited = [deploy_id for claim in answer.findings for deploy_id in claim.deploy_ids]
        unknown = set(cited) - shown.keys()
        if unknown:
            raise ValueError(f"model cited deploys it was not shown: {sorted(unknown)}")
        collected_at = datetime.now(UTC)
        return SpecialistReport(
            specialist=Specialist.DEPLOY,
            summary=answer.summary,
            findings=[
                Finding(specialist=Specialist.DEPLOY, claim=c.claim, evidence_ids=c.deploy_ids)
                for c in answer.findings
            ],
            evidence=[
                _evidence(shown[deploy_id], run_id, collected_at)
                for deploy_id in dict.fromkeys(cited)
            ],
        )


def _evidence(deploy: Deploy, run_id: UUID, collected_at: datetime) -> Evidence:
    """One record per cited deploy."""
    diff = ", ".join(
        f"{key} {change.get('old')}->{change.get('new')}"
        for key, change in deploy.config_diff.items()
    )
    excerpt = (
        f"{deploy.service} {deploy.previous_version}->{deploy.version}: {deploy.change_summary}"
    )
    if diff:
        excerpt += f"; {diff}"
    return Evidence(
        id=deploy.id,
        run_id=run_id,
        source_type=EvidenceSource.DEPLOY,
        source_locator=f"deploys.json#{deploy.id}",
        service=deploy.service,
        event_time=deploy.deployed_at,
        collected_at=collected_at,
        payload_hash=hash_payload(deploy.model_dump(mode="json")),
        excerpt=excerpt,
        metadata={
            "version": deploy.version,
            "previous_version": deploy.previous_version,
            "commit": deploy.commit,
            "author": deploy.author,
        },
    )
