"""Calls the local Ollama model. Run with: uv run pytest -m integration -s"""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from tracehound.agents.inference import OllamaLLM
from tracehound.agents.triage import TriageAgent
from tracehound.schemas import IncidentRecord

SCENARIO = Path(__file__).resolve().parents[2] / "scenarios" / "checkout_db_pool_exhaustion"

pytestmark = [
    pytest.mark.integration,
]


def test_live_triage_scopes_checkout_incident() -> None:
    alert = json.loads((SCENARIO / "scenario.json").read_text())["alert"]
    now = datetime.now(UTC)
    incident = IncidentRecord(
        id=uuid4(), run_id=uuid4(), state="created", created_at=now, updated_at=now, **alert
    )
    scope = TriageAgent(SCENARIO, OllamaLLM())(incident)
    assert {"checkout-api", "orders-db"} <= set(scope.services)
