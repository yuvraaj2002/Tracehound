"""Stored outcome of an investigation run, as returned by ``GET /v1/incidents/{id}``."""

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field

from tracehound.schemas.evidence import Evidence
from tracehound.schemas.finding import Finding
from tracehound.schemas.hypothesis import Hypothesis
from tracehound.schemas.incident import IncidentRecord
from tracehound.schemas.triage import InvestigationScope


class IncidentState(StrEnum):
    """Lifecycle of `incidents.state`. New incidents start CREATED (the column default)."""

    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


AgentName = Literal["triage", "logs", "metrics", "deploy", "dependency", "hypothesis"]


class AgentRun(BaseModel):
    """How one graph node went. A failed specialist leaves the others' results usable."""

    status: Literal["running", "completed", "failed"]
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None
    error: str | None = None


class InvestigationResult(BaseModel):
    """One row of `investigation_results`: everything the graph produced for an incident."""

    incident_id: UUID
    run_id: UUID
    scope: InvestigationScope | None = None
    findings: list[Finding] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)  # sorted by event_time
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    agent_runs: dict[AgentName, AgentRun] = Field(default_factory=dict)
    error: str | None = None
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None


class IncidentDetail(BaseModel):
    """An incident with its investigation result, or `result: null` before a run has stored one."""

    incident: IncidentRecord
    result: InvestigationResult | None = None
