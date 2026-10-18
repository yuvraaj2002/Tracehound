"""The investigation graph. Stages are wired here; agents are passed in already configured."""

from collections.abc import Callable

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer

from tracehound.orchestrator.state import InvestigationState
from tracehound.schemas.incident import IncidentRecord
from tracehound.schemas.triage import InvestigationScope

Triage = Callable[[IncidentRecord], InvestigationScope]


def build_graph(triage: Triage, checkpointer: Checkpointer = None) -> CompiledStateGraph:
    def triage_node(state: InvestigationState) -> dict[str, InvestigationScope]:
        return {"scope": triage(state["incident"])}

    builder = StateGraph(InvestigationState)
    builder.add_node("triage", triage_node)
    builder.add_edge(START, "triage")
    builder.add_edge("triage", END)
    return builder.compile(checkpointer=checkpointer)
