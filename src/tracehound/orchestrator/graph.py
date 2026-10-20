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
    """Triage, then the specialists it selected in parallel, then one hypothesis step over them."""

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
    builder.add_conditional_edges("triage", partial(_selected, specialists), list(specialists))
    for name, specialist in specialists.items():
        builder.add_node(name, partial(_run_specialist, specialist))
        # A plain edge, not a list join: a join would wait forever on skipped specialists.
        # The selected ones run in the same step, so hypothesis runs once, after all of them.
        builder.add_edge(name, "hypothesis")
    builder.add_node("hypothesis", hypothesis_node)
    builder.add_edge("hypothesis", END)
    return builder.compile(checkpointer=checkpointer)


def _selected(specialists: Mapping[str, Specialist], state: InvestigationState) -> list[str]:
    """The specialist nodes triage gave a task to."""
    chosen = [str(task.specialist) for task in state["scope"].tasks]
    missing = set(chosen) - set(specialists)
    if missing:
        raise RuntimeError(f"triage selected specialists with no node: {sorted(missing)}")
    return chosen


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
