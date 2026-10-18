"""The investigation graph. Stages are wired here; agents are passed in already configured."""

from collections.abc import Callable, Mapping
from functools import partial
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer

from tracehound.orchestrator.state import InvestigationState
from tracehound.schemas.evidence import Evidence, EvidenceId
from tracehound.schemas.finding import Finding, SpecialistReport
from tracehound.schemas.hypothesis import Hypothesis
from tracehound.schemas.incident import IncidentRecord
from tracehound.schemas.triage import InvestigationScope

Triage = Callable[[IncidentRecord], InvestigationScope]
Specialist = Callable[[InvestigationScope, UUID], SpecialistReport]
Hypothesize = Callable[
    [IncidentRecord, list[Finding], dict[EvidenceId, Evidence]], list[Hypothesis]
]


def build_graph(
    triage: Triage,
    specialists: Mapping[str, Specialist],
    hypothesize: Hypothesize,
    checkpointer: Checkpointer = None,
) -> CompiledStateGraph:
    """Triage, then every specialist in parallel, then one hypothesis step over all of them."""

    def triage_node(state: InvestigationState) -> dict[str, InvestigationScope]:
        return {"scope": triage(state["incident"])}

    def hypothesis_node(state: InvestigationState) -> dict[str, list[Hypothesis]]:
        return {
            "hypotheses": hypothesize(
                state["incident"], state.get("findings", []), state.get("evidence", {})
            )
        }

    builder = StateGraph(InvestigationState)
    builder.add_node("triage", triage_node)
    builder.add_edge(START, "triage")
    for name, specialist in specialists.items():
        builder.add_node(name, partial(_run_specialist, specialist))
        builder.add_edge("triage", name)
    # One edge from the whole list: hypothesis waits until every specialist has finished.
    builder.add_node("hypothesis", hypothesis_node)
    builder.add_edge(list(specialists), "hypothesis")
    builder.add_edge("hypothesis", END)
    return builder.compile(checkpointer=checkpointer)


def _run_specialist(specialist: Specialist, state: InvestigationState) -> dict[str, object]:
    """Run one specialist on the triage scope and return its results as state updates."""
    scope = state.get("scope")
    if scope is None:
        raise RuntimeError("specialist ran before triage produced a scope")
    report = specialist(scope, state["incident"].run_id)
    return {
        "findings": report.findings,
        "evidence": {item.id: item for item in report.evidence},
    }
