"""Run only the triage agent on a scenario and print what goes in and comes out.

Usage: uv run python scripts/run_triage.py [scenario_name]
"""

import json
import sys
from datetime import UTC, datetime
from uuid import uuid4

from run_investigation import ROOT, PrintingLLM

from tracehound.agents.triage import TriageAgent
from tracehound.schemas import IncidentRecord


def main() -> None:
    scenario = (
        ROOT / "scenarios" / (sys.argv[1] if len(sys.argv) > 1 else "checkout_db_pool_exhaustion")
    )
    alert = json.loads((scenario / "scenario.json").read_text())["alert"]
    now = datetime.now(UTC)
    incident = IncidentRecord(
        id=uuid4(), run_id=uuid4(), state="created", created_at=now, updated_at=now, **alert
    )
    print("===== INCIDENT =====")
    print(incident.model_dump_json(indent=2))

    scope = TriageAgent(scenario, PrintingLLM())(incident)

    print("\n===== INVESTIGATION SCOPE =====")
    print(scope.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
