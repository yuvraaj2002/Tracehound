"""The investigation graph. Stages are wired here; agents are passed in already configured."""

from collections.abc import Callable, Mapping
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer

from tracehound.orchestrator.state import InvestigationState
from tracehound.schemas.finding import SpecialistReport
from tracehound.schemas.incident import IncidentRecord
from tracehound.schemas.triage import InvestigationScope

Triage = Callable[[IncidentRecord], InvestigationScope]
Specialist = Callable[[InvestigationScope, UUID], SpecialistReport]


def build_graph(
    triage: Triage, specialists: Mapping[str, Specialist], checkpointer: Checkpointer = None
) -> CompiledStateGraph:
    """Triage first, then every specialist in parallel. Their results merge through reducers."""

    def triage_node(state: InvestigationState) -> dict[str, InvestigationScope]:
        return {"scope": triage(state["incident"])}

    builder = StateGraph(InvestigationState)
    builder.add_node("triage", triage_node)
    builder.add_edge(START, "triage")
    for name, specialist in specialists.items():
        builder.add_node(name, _specialist_node(specialist))
        builder.add_edge("triage", name)
        builder.add_edge(name, END)
    return builder.compile(checkpointer=checkpointer)


def _specialist_node(specialist: Specialist) -> Callable[[InvestigationState], dict[str, object]]:
    def node(state: InvestigationState) -> dict[str, object]:
        report = specialist(state["scope"], state["incident"].run_id)
        return {
            "findings": report.findings,
            "evidence": {item.id: item for item in report.evidence},
        }

    return node
