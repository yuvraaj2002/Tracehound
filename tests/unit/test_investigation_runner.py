from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from tracehound.schemas import IncidentRecord
from tracehound.schemas.finding import SpecialistReport
from tracehound.schemas.hypothesis import Hypothesis
from tracehound.schemas.investigation import AgentRun
from tracehound.schemas.triage import InvestigationScope, Specialist, SpecialistTask
from tracehound.worker.runner import (
    LIVE_NOT_SUPPORTED,
    Agents,
    InvestigationRunner,
    LiveSetupMissing,
)

SCENARIO = Path(__file__).resolve().parents[2] / "scenarios" / "checkout_db_pool_exhaustion"
FIXTURE_USER = uuid4()


class StubStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.agents: dict[str, list[AgentRun]] = {}

    def start(self, incident_id: UUID, user_id: UUID, run_id: UUID) -> None:
        self.calls.append(("start", incident_id))

    def record_agent(self, incident_id: UUID, agent: str, run: AgentRun) -> None:
        self.agents.setdefault(agent, []).append(run)

    def complete(self, incident_id: UUID, scope, findings, evidence, hypotheses) -> None:  # type: ignore[no-untyped-def]
        self.calls.append(("complete", (scope, list(findings), list(evidence), list(hypotheses))))

    def fail(
        self, incident_id: UUID, error: str, scope=None, findings=(), evidence=(), hypotheses=()
    ) -> None:  # type: ignore[no-untyped-def]
        self.calls.append(("fail", (error, scope)))


def _incident() -> IncidentRecord:
    now = datetime.now(UTC)
    return IncidentRecord(
        id=uuid4(),
        run_id=uuid4(),
        service_id="anything",
        symptom="slow",
        severity="high",
        window_start=now,
        window_end=now,
        trace_id=None,
        state="CREATED",
        created_at=now,
        updated_at=now,
    )


def _scope(incident: IncidentRecord) -> InvestigationScope:
    return InvestigationScope(
        alert_service=incident.service_id,
        services=[incident.service_id],
        symptom_window_start=incident.window_start,
        symptom_window_end=incident.window_end,
        change_window_start=incident.window_start,
        tasks=[
            SpecialistTask(
                specialist=Specialist.LOGS, question="q", services=[incident.service_id]
            ),
            SpecialistTask(
                specialist=Specialist.METRICS, question="q", services=[incident.service_id]
            ),
        ],
        rationale="r",
    )


def _agents(*, fail_logs: bool = False, fail_triage: bool = False) -> Agents:
    seen: dict[str, IncidentRecord] = {}

    def triage(incident: IncidentRecord) -> InvestigationScope:
        seen["incident"] = incident
        if fail_triage:
            raise ConnectionError("ollama unreachable")
        return _scope(incident)

    def specialist(name: Specialist, fail: bool):  # type: ignore[no-untyped-def]
        def run(scope: InvestigationScope, run_id: UUID) -> SpecialistReport:
            if fail:
                raise RuntimeError("boom")
            return SpecialistReport(specialist=name, summary="ok", findings=[], evidence=[])

        return run

    def hypothesize(incident, findings, evidence) -> list[Hypothesis]:  # type: ignore[no-untyped-def]
        return []

    return Agents(
        triage=triage,
        specialists={
            "logs": specialist(Specialist.LOGS, fail_logs),
            "metrics": specialist(Specialist.METRICS, False),
        },
        hypothesize=hypothesize,
    )


def _runner(store: StubStore, agents: Agents) -> InvestigationRunner:
    return InvestigationRunner(
        store,
        fixture_users=frozenset({FIXTURE_USER}),
        scenario=SCENARIO,
        agents_factory=lambda _: agents,
        max_workers=1,
    )


def test_fixture_user_run_completes_and_tracks_agents() -> None:
    store = StubStore()
    _runner(store, _agents()).run(_incident(), FIXTURE_USER)
    assert [name for name, _ in store.calls] == ["start", "complete"]
    assert {k: [r.status for r in v] for k, v in store.agents.items()} == {
        "triage": ["running", "completed"],
        "logs": ["running", "completed"],
        "metrics": ["running", "completed"],
        "hypothesis": ["running", "completed"],
    }
    scope = store.calls[1][1][0]
    # The graph sees the scenario's alert window, not the submitted one.
    assert scope.alert_service == "checkout-api"


def test_failed_specialist_is_recorded_and_others_still_count() -> None:
    store = StubStore()
    _runner(store, _agents(fail_logs=True)).run(_incident(), FIXTURE_USER)
    assert store.calls[-1][0] == "complete"
    assert store.agents["logs"][-1].status == "failed"
    assert store.agents["logs"][-1].error == "RuntimeError: boom"
    assert store.agents["metrics"][-1].status == "completed"


def test_non_fixture_user_fails_without_running_agents() -> None:
    store = StubStore()
    _runner(store, _agents()).run(_incident(), uuid4())
    assert store.calls[-1] == ("fail", (LIVE_NOT_SUPPORTED, None))
    assert store.agents == {}


def test_exception_fails_the_run() -> None:
    store = StubStore()
    _runner(store, _agents(fail_triage=True)).run(_incident(), FIXTURE_USER)
    name, (error, _) = store.calls[-1]
    assert name == "fail"
    assert "ollama unreachable" in error
    assert store.agents["triage"][-1].status == "failed"


def test_submit_runs_in_background() -> None:
    store = StubStore()
    runner = _runner(store, _agents())
    runner.submit(_incident(), FIXTURE_USER).result(timeout=10)
    assert store.calls[-1][0] == "complete"


@pytest.fixture(autouse=True)
def _scenario_exists() -> None:
    assert (SCENARIO / "scenario.json").exists()


def _live_runner(store: StubStore, factory) -> InvestigationRunner:  # type: ignore[no-untyped-def]
    return InvestigationRunner(
        store,
        fixture_users=frozenset({FIXTURE_USER}),
        scenario=SCENARIO,
        agents_factory=lambda _: pytest.fail("live users must not read scenario files"),
        live_agents=factory,
        max_workers=1,
    )


def test_live_user_runs_their_own_agents_over_the_submitted_window() -> None:
    store = StubStore()
    opened: list[tuple[UUID, str]] = []
    closed: list[bool] = []

    @contextmanager
    def factory(user_id: UUID, alert: str) -> Iterator[Agents]:
        opened.append((user_id, alert))
        yield _agents()
        closed.append(True)

    incident = _incident()
    incident = incident.model_copy(
        update={"window_start": incident.window_end - timedelta(minutes=10)}
    )
    user = uuid4()
    _live_runner(store, factory).run(incident, user)
    assert [name for name, _ in store.calls] == ["start", "complete"]
    assert opened == [(user, "anything")] and closed == [True]
    scope = store.calls[1][1][0]
    assert (scope.alert_service, scope.symptom_window_start) == ("anything", incident.window_start)


def test_live_setup_missing_fails_with_its_reason() -> None:
    store = StubStore()

    @contextmanager
    def factory(user_id: UUID, alert: str) -> Iterator[Agents]:
        raise LiveSetupMissing("Connect these integrations first: tempo.")
        yield _agents()

    _live_runner(store, factory).run(_incident(), uuid4())
    assert store.calls[-1] == ("fail", ("Connect these integrations first: tempo.", None))
    assert store.agents == {}
