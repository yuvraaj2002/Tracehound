"""Specialist output: observations, each backed by the evidence that supports it."""

from pydantic import BaseModel, ConfigDict, Field

from tracehound.schemas.evidence import Evidence, EvidenceId
from tracehound.schemas.triage import Specialist


class Finding(BaseModel):
    """One observation a specialist made, citing evidence by ID."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    specialist: Specialist
    claim: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class SpecialistReport(BaseModel):
    """Everything one specialist returns. Every cited ID has a matching Evidence record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    specialist: Specialist
    summary: str = Field(min_length=1, max_length=2000)
    findings: list[Finding]
    evidence: list[Evidence]
