"""Calls the real model. Run with: ANTHROPIC_API_KEY=... uv run pytest -m integration"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from tracehound.agents.llm import AnthropicLLM
from tracehound.agents.triage import TriageAgent
from tracehound.schemas import IncidentRecord, TriagePlanner
from tracehound.tools.scenario import ScenarioTelemetry

SCENARIO = Path(__file__).resolve().parents[2] / "scenarios" / "checkout_db_pool_exhaustion"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY"),
]


def test_live_triage_scopes_checkout_incident() -> None:
    alert = json.loads((SCENARIO / "scenario.json").read_text())["alert"]
    now = datetime.now(UTC)
    incident = IncidentRecord(
        id=uuid4(), run_id=uuid4(), state="created", created_at=now, updated_at=now, **alert
    )
    scope = TriageAgent(ScenarioTelemetry(SCENARIO), AnthropicLLM())(incident)
    assert scope.planner is TriagePlanner.LLM, scope.fallback_reason
    assert {"checkout-api", "orders-db"} <= set(scope.services)
