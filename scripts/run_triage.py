"""Run the investigation graph (triage only, for now) on a scenario and print each stage.

Usage: uv run python scripts/run_triage.py [scenario_name]
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver

from tracehound.agents.llm import OllamaLLM
from tracehound.agents.triage import TriageAgent
from tracehound.orchestrator.graph import build_graph
from tracehound.orchestrator.state import SERDE
from tracehound.schemas import IncidentRecord

ROOT = Path(__file__).resolve().parents[1]


class PrintingLLM(OllamaLLM):
    """Shows exactly what goes to the model and what comes back."""

    def generate(self, *, system, user, schema):
        print(f"\n===== 2. CONTEXT SENT TO {self.model} =====\n{user}")
        result = super().generate(system=system, user=user, schema=schema)
        print(f"\n===== 3. LLM OUTPUT ({schema.__name__}) =====")
        print(result.model_dump_json(indent=2))
        return result


def main() -> None:
    scenario = (
        ROOT / "scenarios" / (sys.argv[1] if len(sys.argv) > 1 else "checkout_db_pool_exhaustion")
    )
    alert = json.loads((scenario / "scenario.json").read_text())["alert"]
    now = datetime.now(UTC)
    incident = IncidentRecord(
        id=uuid4(), run_id=uuid4(), state="created", created_at=now, updated_at=now, **alert
    )
    print("===== 1. INCIDENT =====")
    print(incident.model_dump_json(indent=2))

    graph = build_graph(
        TriageAgent(scenario, PrintingLLM()), checkpointer=InMemorySaver(serde=SERDE)
    )
    config = {"configurable": {"thread_id": str(incident.run_id)}}
    state = graph.invoke({"incident": incident}, config)

    print("\n===== 4. SCOPE IN GRAPH STATE =====")
    print(state["scope"].model_dump_json(indent=2))


if __name__ == "__main__":
    main()
