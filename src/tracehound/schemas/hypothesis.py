"""Hypothesis contracts: candidate root causes tied to cited evidence."""

from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tracehound.schemas.evidence import EvidenceId


class ConfidenceBand(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class HypothesisStatus(StrEnum):
    PROPOSED = "proposed"
    SUPPORTED = "supported"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"


class VerificationStep(BaseModel):
    """A check that would confirm or refute a hypothesis."""

    model_config = ConfigDict(extra="forbid")

    check: str = Field(min_length=1, max_length=1000)
    expected_if_true: str = Field(min_length=1, max_length=1000)


class Hypothesis(BaseModel):
    """A candidate root cause. Every claim cites evidence by ID."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    statement: str = Field(min_length=1, max_length=1000)
    mechanism: str = Field(min_length=1, max_length=2000)
    confidence: ConfidenceBand
    confidence_rationale: str = Field(min_length=1, max_length=2000)
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    supporting_evidence_ids: list[EvidenceId] = Field(default_factory=list)
    contradicting_evidence_ids: list[EvidenceId] = Field(default_factory=list)
    verification_steps: list[VerificationStep] = Field(default_factory=list)

    @field_validator("supporting_evidence_ids", "contradicting_evidence_ids")
    @classmethod
    def _ids_are_unique(cls, ids: list[str]) -> list[str]:
        if len(ids) != len(set(ids)):
            raise ValueError("evidence IDs must be unique")
        return ids

    @model_validator(mode="after")
    def _citations_match_status(self) -> Self:
        overlap = set(self.supporting_evidence_ids) & set(self.contradicting_evidence_ids)
        if overlap:
            raise ValueError(f"evidence cannot both support and contradict: {sorted(overlap)}")
        if self.status is HypothesisStatus.REFUTED:
            if not self.contradicting_evidence_ids:
                raise ValueError("a refuted hypothesis must cite contradicting evidence")
        elif not self.supporting_evidence_ids:
            raise ValueError(f"a {self.status} hypothesis must cite supporting evidence")
        return self

    @property
    def cited_evidence_ids(self) -> set[EvidenceId]:
        """Every evidence ID this hypothesis relies on, for checking against the store."""
        return {*self.supporting_evidence_ids, *self.contradicting_evidence_ids}
