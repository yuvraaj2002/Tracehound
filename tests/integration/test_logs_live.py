"""Calls the local Ollama model. Run with: uv run pytest -m integration -s"""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from tracehound.agents.inference import OllamaLLM
from tracehound.agents.logs import LogsAgent
from tracehound.agents.triage import TriageAgent
from tracehound.schemas import IncidentRecord, Specialist
from tracehound.tools.logs import FileLogSource

SCENARIO = Path(__file__).resolve().parents[2] / "scenarios" / "checkout_db_pool_exhaustion"

pytestmark = [
    pytest.mark.integration,
]


def test_live_logs_cites_pool_timeouts() -> None:
    alert = json.loads((SCENARIO / "scenario.json").read_text())["alert"]
    now = datetime.now(UTC)
    incident = IncidentRecord(
        id=uuid4(), run_id=uuid4(), state="created", created_at=now, updated_at=now, **alert
    )
    llm = OllamaLLM()
    scope = TriageAgent(SCENARIO, llm)(incident)
    if Specialist.LOGS not in {task.specialist for task in scope.tasks}:
        pytest.skip("live triage did not select the logs specialist")
    report = LogsAgent(FileLogSource(SCENARIO), llm)(scope, incident.run_id)

    assert report.findings
    assert any("QueuePool" in item.excerpt for item in report.evidence)
