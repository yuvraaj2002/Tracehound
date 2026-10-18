"""Triage agent: turns an incident into an InvestigationScope."""

import logging
from datetime import datetime, timedelta
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from tracehound.agents.llm import LLMError, StructuredLLM
from tracehound.agents.triage.prompt import SYSTEM_PROMPT, TriageContext, render_user_message
from tracehound.schemas.incident import IncidentRecord
from tracehound.schemas.telemetry import Deploy, ServiceNode, Topology
from tracehound.schemas.triage import (
    InvestigationScope,
    Specialist,
    SpecialistTask,
    TriagePlanner,
)

logger = logging.getLogger(__name__)

CHANGE_LOOKBACK = timedelta(hours=1)
"""How far before the symptom window to look for deploys. Changes often precede symptoms."""


class TriageTelemetry(Protocol):
    def topology(self) -> Topology: ...
    def deploys(self, services: set[str], start: datetime, end: datetime) -> list[Deploy]: ...


class TriageDecision(BaseModel):
    """What the model decides. Windows and services are checked against the context after."""

    model_config = ConfigDict(extra="forbid")

    services: list[str] = Field(description="In-scope services, chosen from the candidates")
    tasks: list[SpecialistTask] = Field(description="Exactly one task per specialist")
    rationale: str


class TriageAgent:
    """Deterministic context gathering, then one LLM call; falls back to rules on any failure."""

    def __init__(self, telemetry: TriageTelemetry, llm: StructuredLLM | None = None) -> None:
        self._telemetry = telemetry
        self._llm = llm

    def __call__(self, incident: IncidentRecord) -> InvestigationScope:
        ctx = self.build_context(incident)
        if self._llm is None:
            return rules_scope(ctx)
        try:
            decision = self._llm.generate(
                system=SYSTEM_PROMPT, user=render_user_message(ctx), schema=TriageDecision
            )
            return scope_from_decision(ctx, decision)
        except (LLMError, ValueError) as exc:  # pydantic.ValidationError is a ValueError
            logger.warning("triage fell back to rules: %s", exc)
            return rules_scope(ctx, fallback_reason=f"{type(exc).__name__}: {exc}"[:500])

    def build_context(self, incident: IncidentRecord) -> TriageContext:
        topology = self._telemetry.topology()
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
            deploys=self._telemetry.deploys(in_reach, change_start, incident.window_end),
            change_window_start=change_start,
        )


def scope_from_decision(ctx: TriageContext, decision: TriageDecision) -> InvestigationScope:
    """Validate the model's choices against what it was shown. Raises ValueError if invalid."""
    candidate_ids = [node.id for node in ctx.candidates]
    unknown = set(decision.services) - set(candidate_ids)
    if unknown:
        raise ValueError(f"model chose services outside the candidates: {sorted(unknown)}")
    alert = ctx.incident.service_id
    services = [s for s in candidate_ids if s == alert or s in decision.services]
    return _scope(ctx, services, decision.tasks, decision.rationale, TriagePlanner.LLM)


def rules_scope(ctx: TriageContext, fallback_reason: str | None = None) -> InvestigationScope:
    """The baseline: every candidate service and a generic question per specialist."""
    incident = ctx.incident
    services = [node.id for node in ctx.candidates]
    listed = ", ".join(services)
    window = f"{incident.window_start:%H:%M}-{incident.window_end:%H:%M}Z"
    trace = (
        f"Where does trace {incident.trace_id} spend its time or fail? "
        if incident.trace_id
        else ""
    )
    questions = {
        Specialist.LOGS: f"Which errors and warnings in {listed} start or grow during {window}, "
        "and which were already present before it?",
        Specialist.METRICS: f"Which metrics for {listed} change around {window}, "
        "and which stay flat?",
        Specialist.DEPLOY: f"What changed in {listed} between "
        f"{ctx.change_window_start:%H:%M}Z and {incident.window_end:%H:%M}Z? "
        "Check every deploy and its config diff.",
        Specialist.DEPENDENCY: f"{trace}Do the dependencies of {incident.service_id} "
        f"show errors or latency during {window}?",
    }
    tasks = [
        SpecialistTask(specialist=s, question=q, services=services) for s, q in questions.items()
    ]
    rationale = (
        f"Rule-based scope: {incident.service_id} and its direct dependencies, the alert window "
        f"for symptoms, and {CHANGE_LOOKBACK} of lookback for changes."
    )
    return _scope(ctx, services, tasks, rationale, TriagePlanner.RULES, fallback_reason)


def _scope(
    ctx: TriageContext,
    services: list[str],
    tasks: list[SpecialistTask],
    rationale: str,
    planner: TriagePlanner,
    fallback_reason: str | None = None,
) -> InvestigationScope:
    return InvestigationScope(
        alert_service=ctx.incident.service_id,
        services=services,
        symptom_window_start=ctx.incident.window_start,
        symptom_window_end=ctx.incident.window_end,
        change_window_start=ctx.change_window_start,
        tasks=tasks,
        rationale=rationale,
        planner=planner,
        fallback_reason=fallback_reason,
    )
