"""LangGraph state shared by every node of an investigation."""

from typing import Annotated, Required, TypedDict

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

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


SERDE = JsonPlusSerializer(
    allowed_msgpack_modules=[
        ("tracehound.schemas.incident", "IncidentRecord"),
        ("tracehound.schemas.incident", "Severity"),
        ("tracehound.schemas.triage", "InvestigationScope"),
        ("tracehound.schemas.triage", "SpecialistTask"),
        ("tracehound.schemas.triage", "Specialist"),
        ("tracehound.schemas.evidence", "Evidence"),
        ("tracehound.schemas.evidence", "EvidenceSource"),
        ("tracehound.schemas.hypothesis", "Hypothesis"),
        ("tracehound.schemas.hypothesis", "HypothesisStatus"),
        ("tracehound.schemas.hypothesis", "ConfidenceBand"),
        ("tracehound.schemas.hypothesis", "VerificationStep"),
    ]
)
"""Checkpoint serializer that only revives our own state types. Pass as ``serde=`` to a saver."""
