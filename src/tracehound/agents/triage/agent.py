"""Triage agent: turns an incident into an InvestigationScope."""

from datetime import datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from tracehound.agents.inference import StructuredLLM
from tracehound.agents.triage.prompt import SYSTEM_PROMPT
from tracehound.schemas.incident import IncidentRecord
from tracehound.schemas.telemetry import Deploy, Edge, ServiceNode, Topology
from tracehound.schemas.triage import InvestigationScope, Specialist, SpecialistTask
from tracehound.tools.deploys import DeploySource, FileDeploySource
from tracehound.tools.triage import load_topology

CHANGE_LOOKBACK = timedelta(hours=1)
"""How far before the symptom window to look for deploys. Changes often precede symptoms."""


class TriageContext(BaseModel):
    """Everything the model is shown, gathered by code before the call."""

    incident: IncidentRecord
    candidates: list[ServiceNode]
    edges: list[Edge]
    change_window_start: datetime
    deploys: list[Deploy]


class TriageDecision(BaseModel):
    """What the model decides. Windows and services are checked against the context after."""

    model_config = ConfigDict(extra="forbid")

    services: list[str] = Field(description="In-scope services, chosen from the candidates")
    logs_question: str | None = Field(default=None, description="Null to skip this specialist")
    metrics_question: str | None = Field(default=None, description="Null to skip this specialist")
    deploy_question: str | None = Field(default=None, description="Null to skip this specialist")
    dependency_question: str | None = Field(
        default=None, description="Null to skip this specialist"
    )
    logs_services: list[str] | None = Field(
        default=None, description="Service names from services; null for all"
    )
    metrics_services: list[str] | None = Field(
        default=None, description="Service names from services; null for all"
    )
    deploy_services: list[str] | None = Field(
        default=None, description="Service names from services; null for all"
    )
    dependency_services: list[str] | None = Field(
        default=None, description="Service names from services; null for all"
    )
    rationale: str


class TriageAgent:
    """Deterministic context gathering, then one LLM call. Errors propagate to the caller.

    ``topology`` says which services are one hop from the alerting one: a scenario's
    topology.json, or the user's uploaded service catalog. ``deploys`` is read for changes to
    those services shortly before the symptoms.
    """

    def __init__(self, topology: Topology, deploys: DeploySource, llm: StructuredLLM) -> None:
        self._topology = topology
        self._deploys = deploys
        self._llm = llm

    @classmethod
    def from_scenario(cls, scenario_dir: Path, llm: StructuredLLM) -> "TriageAgent":
        """Triage over a scenario folder's topology.json and deploys.json."""
        return cls(load_topology(scenario_dir), FileDeploySource(scenario_dir), llm)

    def __call__(self, incident: IncidentRecord) -> InvestigationScope:
        ctx = self.build_context(incident)
        # Escaping <> keeps the JSON valid but stops untrusted text from closing the tag.
        data = ctx.model_dump_json(indent=2).replace("<", "\\u003c").replace(">", "\\u003e")
        decision = self._llm.generate(
            system=SYSTEM_PROMPT, user=f"<context>\n{data}\n</context>", schema=TriageDecision
        )
        return self.scope_from_decision(ctx, decision)

    def build_context(self, incident: IncidentRecord) -> TriageContext:
        topology = self._topology
        alert = incident.service_id
        in_reach = {alert} | topology.neighbors(alert)
        known = {node.id: node for node in topology.services}
        candidates = [known.get(alert) or ServiceNode(id=alert, kind="unknown", team="unknown")]
        candidates += [known[s] for s in sorted(in_reach - {alert}) if s in known]
        change_start = incident.window_start - CHANGE_LOOKBACK
        return TriageContext(
            incident=incident,
            candidates=candidates,
            edges=topology.edges_touching(in_reach),
            deploys=self._deploys.fetch(in_reach, change_start, incident.window_end),
            change_window_start=change_start,
        )

    @staticmethod
    def scope_from_decision(ctx: TriageContext, decision: TriageDecision) -> InvestigationScope:
        """Validate the model's choices against what it was shown. Raises ValueError if invalid."""
        candidate_ids = [node.id for node in ctx.candidates]
        unknown = set(decision.services) - set(candidate_ids)
        if unknown:
            raise ValueError(f"model chose services outside the candidates: {sorted(unknown)}")
        questions = {s: getattr(decision, f"{s}_question") for s in Specialist}
        questions = {s: q for s, q in questions.items() if q and q.strip()}
        if not questions:
            raise ValueError("model selected no specialists")
        alert = ctx.incident.service_id
        services = [s for s in candidate_ids if s == alert or s in decision.services]
        return InvestigationScope(
            alert_service=alert,
            services=services,
            symptom_window_start=ctx.incident.window_start,
            symptom_window_end=ctx.incident.window_end,
            change_window_start=ctx.change_window_start,
            tasks=[
                SpecialistTask(
                    specialist=s,
                    question=q,
                    services=_task_services(s, decision, services, alert),
                )
                for s, q in questions.items()
            ],
            rationale=decision.rationale,
        )


def _task_services(
    specialist: Specialist, decision: TriageDecision, in_scope: list[str], alert: str
) -> list[str]:
    """The services one specialist looks at, always with the alert service.

    Names outside the scope are dropped rather than raised on: narrowing is optional, and a bad
    pick should widen the search back to the whole scope, not fail the run.
    """
    chosen = set(getattr(decision, f"{specialist}_services") or []) & set(in_scope)
    if not chosen:
        return in_scope
    return [s for s in in_scope if s == alert or s in chosen]
