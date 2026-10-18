"""Triage agent: turns an incident into an InvestigationScope."""

from datetime import datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from tracehound.agents.llm import StructuredLLM
from tracehound.agents.triage.prompt import SYSTEM_PROMPT
from tracehound.schemas.incident import IncidentRecord
from tracehound.schemas.telemetry import Deploy, Edge, ServiceNode
from tracehound.schemas.triage import InvestigationScope, Specialist, SpecialistTask
from tracehound.tools.scenario import load_deploys, load_topology

CHANGE_LOOKBACK = timedelta(hours=1)
"""How far before the symptom window to look for deploys. Changes often precede symptoms."""


class TriageContext(BaseModel):
    """Everything the model is shown, gathered by code before the call."""

    incident: IncidentRecord
    candidates: list[ServiceNode]
    edges: list[Edge]
    change_window_start: datetime
    deploys: list[Deploy]


class TaskQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    specialist: Specialist
    question: str


class TriageDecision(BaseModel):
    """What the model decides. Windows and services are checked against the context after."""

    model_config = ConfigDict(extra="forbid")

    services: list[str] = Field(description="In-scope services, chosen from the candidates")
    tasks: list[TaskQuestion] = Field(description="Exactly one question per specialist")
    rationale: str


class TriageAgent:
    """Deterministic context gathering, then one LLM call. Errors propagate to the caller."""

    def __init__(self, scenario_dir: Path, llm: StructuredLLM) -> None:
        self._scenario_dir = scenario_dir
        self._llm = llm

    def __call__(self, incident: IncidentRecord) -> InvestigationScope:
        ctx = self.build_context(incident)
        # Escaping <> keeps the JSON valid but stops untrusted text from closing the tag.
        data = ctx.model_dump_json(indent=2).replace("<", "\\u003c").replace(">", "\\u003e")
        decision = self._llm.generate(
            system=SYSTEM_PROMPT, user=f"<context>\n{data}\n</context>", schema=TriageDecision
        )
        return self.scope_from_decision(ctx, decision)

    def build_context(self, incident: IncidentRecord) -> TriageContext:
        topology = load_topology(self._scenario_dir)
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
            deploys=load_deploys(self._scenario_dir, in_reach, change_start, incident.window_end),
            change_window_start=change_start,
        )

    @staticmethod
    def scope_from_decision(ctx: TriageContext, decision: TriageDecision) -> InvestigationScope:
        """Validate the model's choices against what it was shown. Raises ValueError if invalid."""
        candidate_ids = [node.id for node in ctx.candidates]
        unknown = set(decision.services) - set(candidate_ids)
        if unknown:
            raise ValueError(f"model chose services outside the candidates: {sorted(unknown)}")
        alert = ctx.incident.service_id
        services = [s for s in candidate_ids if s == alert or s in decision.services]
        return InvestigationScope(
            alert_service=alert,
            services=services,
            symptom_window_start=ctx.incident.window_start,
            symptom_window_end=ctx.incident.window_end,
            change_window_start=ctx.change_window_start,
            tasks=[SpecialistTask(**t.model_dump(), services=services) for t in decision.tasks],
            rationale=decision.rationale,
        )
