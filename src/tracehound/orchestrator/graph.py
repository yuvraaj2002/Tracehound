"""The investigation graph. Stages are wired here; agents are passed in already configured."""

from collections.abc import Callable
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
    triage: Triage, logs: Specialist, checkpointer: Checkpointer = None
) -> CompiledStateGraph:
    def triage_node(state: InvestigationState) -> dict[str, InvestigationScope]:
        return {"scope": triage(state["incident"])}

    def logs_node(state: InvestigationState) -> dict[str, object]:
        report = logs(state["scope"], state["incident"].run_id)
        return {
            "findings": report.findings,
            "evidence": {item.id: item for item in report.evidence},
        }

    builder = StateGraph(InvestigationState)
    builder.add_node("triage", triage_node)
    builder.add_node("logs", logs_node)
    builder.add_edge(START, "triage")
    builder.add_edge("triage", "logs")
    builder.add_edge("logs", END)
    return builder.compile(checkpointer=checkpointer)
