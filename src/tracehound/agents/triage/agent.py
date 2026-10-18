"""Triage agent: turns an incident into an InvestigationScope."""

from datetime import timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from tracehound.agents.llm import StructuredLLM
from tracehound.agents.triage.prompt import SYSTEM_PROMPT, TriageContext, render_user_message
from tracehound.schemas.incident import IncidentRecord
from tracehound.schemas.telemetry import ServiceNode
from tracehound.schemas.triage import InvestigationScope, SpecialistTask
from tracehound.tools.scenario import load_deploys, load_topology

CHANGE_LOOKBACK = timedelta(hours=1)
"""How far before the symptom window to look for deploys. Changes often precede symptoms."""


class TriageDecision(BaseModel):
    """What the model decides. Windows and services are checked against the context after."""

    model_config = ConfigDict(extra="forbid")

    services: list[str] = Field(description="In-scope services, chosen from the candidates")
    tasks: list[SpecialistTask] = Field(description="Exactly one task per specialist")
    rationale: str


class TriageAgent:
    """Deterministic context gathering, then one LLM call. Errors propagate to the caller."""

    def __init__(self, scenario_dir: Path, llm: StructuredLLM) -> None:
        self._scenario_dir = scenario_dir
        self._llm = llm

    def __call__(self, incident: IncidentRecord) -> InvestigationScope:
        ctx = self.build_context(incident)
        decision = self._llm.generate(
            system=SYSTEM_PROMPT, user=render_user_message(ctx), schema=TriageDecision
        )
        return scope_from_decision(ctx, decision)

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


def scope_from_decision(ctx: TriageContext, decision: TriageDecision) -> InvestigationScope:
    """Validate the model's choices against what it was shown. Raises ValueError if invalid."""
    candidate_ids = [node.id for node in ctx.candidates]
    unknown = set(decision.services) - set(candidate_ids)
    if unknown:
        raise ValueError(f"model chose services outside the candidates: {sorted(unknown)}")
    alert = ctx.incident.service_id
    return InvestigationScope(
        alert_service=alert,
        services=[s for s in candidate_ids if s == alert or s in decision.services],
        symptom_window_start=ctx.incident.window_start,
        symptom_window_end=ctx.incident.window_end,
        change_window_start=ctx.change_window_start,
        tasks=decision.tasks,
        rationale=decision.rationale,
    )
