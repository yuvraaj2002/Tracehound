"""Run the investigation graph on a scenario and print each stage.

Usage: uv run python scripts/run_investigation.py [scenario_name]

Each run is saved to runs/<time>_<scenario>/: output.txt (everything printed) and state.json
(the final graph state). Re-read one with: cat runs/<folder>/output.txt
"""

import json
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver

from tracehound.agents.dependency import DependencyAgent
from tracehound.agents.deploy import DeployAgent
from tracehound.agents.hypothesis import HypothesisAgent
from tracehound.agents.inference import OllamaLLM
from tracehound.agents.logs import LogsAgent
from tracehound.agents.metrics import MetricsAgent
from tracehound.agents.triage import TriageAgent
from tracehound.orchestrator.graph import build_graph
from tracehound.orchestrator.state import SERDE
from tracehound.schemas import IncidentRecord

ROOT = Path(__file__).resolve().parents[1]


class Tee:
    """Writes to the terminal and a file at once."""

    def __init__(self, *streams: TextIO) -> None:
        self._streams = streams

    def write(self, text: str) -> None:
        for stream in self._streams:
            stream.write(text)

    def flush(self) -> None:
        for stream in self._streams:
            stream.flush()


class PrintingLLM(OllamaLLM):
    """Shows exactly what goes to the model and what comes back.

    Specialists run in parallel, so each call prints its context and output together.
    """

    _lock = threading.Lock()

    def generate(self, *, system, user, schema):
        result = super().generate(system=system, user=user, schema=schema)
        with self._lock:
            print(f"\n===== CONTEXT SENT TO {self.model} ({schema.__name__}) =====\n{user}")
            print(f"\n===== LLM OUTPUT ({schema.__name__}) =====")
            print(result.model_dump_json(indent=2))
        return result


def main() -> None:
    scenario = (
        ROOT / "scenarios" / (sys.argv[1] if len(sys.argv) > 1 else "checkout_db_pool_exhaustion")
    )
    alert = json.loads((scenario / "scenario.json").read_text())["alert"]
    now = datetime.now(UTC)
    run_dir = ROOT / "runs" / f"{now:%Y%m%d-%H%M%S}_{scenario.name}"
    run_dir.mkdir(parents=True)
    with (run_dir / "output.txt").open("w") as out:
        sys.stdout = Tee(sys.__stdout__, out)
        try:
            run(scenario, alert, now, run_dir)
        finally:
            sys.stdout = sys.__stdout__
    print(f"\nSaved to {run_dir.relative_to(ROOT)}/")


def run(scenario: Path, alert: dict, now: datetime, run_dir: Path) -> None:
    incident = IncidentRecord(
        id=uuid4(), run_id=uuid4(), state="created", created_at=now, updated_at=now, **alert
    )
    print("===== INCIDENT =====")
    print(incident.model_dump_json(indent=2))

    llm = PrintingLLM()
    graph = build_graph(
        TriageAgent(scenario, llm),
        {
            "logs": LogsAgent(scenario, llm),
            "metrics": MetricsAgent(scenario, llm),
            "deploy": DeployAgent(scenario, llm),
            "dependency": DependencyAgent(scenario, llm),
        },
        HypothesisAgent(llm),
        checkpointer=InMemorySaver(serde=SERDE),
    )
    config = {"configurable": {"thread_id": str(incident.run_id)}}
    state = graph.invoke({"incident": incident}, config)

    print("\n===== SCOPE IN GRAPH STATE =====")
    print(state["scope"].model_dump_json(indent=2))
    print("\n===== FINDINGS IN GRAPH STATE =====")
    for finding in state["findings"]:
        print(f"[{finding.specialist}] {finding.claim}  <- {', '.join(finding.evidence_ids)}")
    print("\n===== EVIDENCE IN GRAPH STATE =====")
    for item in state["evidence"].values():
        print(f"{item.id}  {item.event_time:%H:%M:%S}  {item.service}  {item.excerpt}")

    print("\n===== HYPOTHESES IN GRAPH STATE =====")
    for h in state["hypotheses"]:
        print(f"[{h.status} / {h.confidence}] {h.statement}")
        print(f"  mechanism: {h.mechanism}")
        print(f"  supports: {', '.join(h.supporting_evidence_ids) or '-'}")
        print(f"  contradicts: {', '.join(h.contradicting_evidence_ids) or '-'}")
        for step in h.verification_steps:
            print(f"  verify: {step.check} -> expect {step.expected_if_true}")

    saved = {
        key: (
            {k: v.model_dump(mode="json") for k, v in value.items()}
            if isinstance(value, dict)
            else [v.model_dump(mode="json") for v in value]
            if isinstance(value, list)
            else value.model_dump(mode="json")
        )
        for key, value in state.items()
    }
    (run_dir / "state.json").write_text(json.dumps(saved, indent=2))


if __name__ == "__main__":
    main()
