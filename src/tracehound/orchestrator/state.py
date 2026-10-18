"""LangGraph state shared by every node of an investigation."""

from typing import Annotated, Required, TypedDict

from tracehound.schemas.evidence import Evidence, EvidenceId
from tracehound.schemas.hypothesis import Hypothesis
from tracehound.schemas.incident import IncidentRecord
from tracehound.schemas.triage import InvestigationScope


def keep_first(
    existing: dict[EvidenceId, Evidence], new: dict[EvidenceId, Evidence]
) -> dict[EvidenceId, Evidence]:
    """Merge evidence by ID; a record already collected is never replaced, so retries are safe."""
    return {**new, **existing}


class InvestigationState(TypedDict, total=False):
    incident: Required[IncidentRecord]
    scope: InvestigationScope
    evidence: Annotated[dict[EvidenceId, Evidence], keep_first]
    hypotheses: list[Hypothesis]
