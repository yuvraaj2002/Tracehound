"""Runs investigations in background threads and stores what each agent did."""

import json
import logging
import os
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Protocol, TypeVar
from uuid import UUID

from fastapi import Depends, Request
from langgraph.checkpoint.memory import InMemorySaver

from tracehound.orchestrator.graph import Hypothesize, Specialist, Triage, build_graph
from tracehound.orchestrator.state import SERDE
from tracehound.schemas.evidence import Evidence
from tracehound.schemas.finding import Finding, SpecialistReport
from tracehound.schemas.hypothesis import Hypothesis
from tracehound.schemas.incident import IncidentRecord
from tracehound.schemas.investigation import AgentName, AgentRun
from tracehound.schemas.triage import InvestigationScope
from tracehound.schemas.triage import Specialist as SpecialistName

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCENARIO = "checkout_db_pool_exhaustion"
LIVE_NOT_SUPPORTED = (
    "Live integrations are not supported yet; only fixture data can be investigated."
)

T = TypeVar("T")


class Store(Protocol):
    """The parts of `InvestigationStore` the runner uses."""

    def start(self, incident_id: UUID, user_id: UUID, run_id: UUID) -> None: ...
    def record_agent(self, incident_id: UUID, agent: AgentName, run: AgentRun) -> None: ...
    def complete(
        self,
        incident_id: UUID,
        scope: InvestigationScope | None,
        findings: Iterable[Finding],
        evidence: Iterable[Evidence],
        hypotheses: Iterable[Hypothesis],
    ) -> None: ...
    def fail(
        self,
        incident_id: UUID,
        error: str,
        scope: InvestigationScope | None = None,
        findings: Iterable[Finding] = (),
        evidence: Iterable[Evidence] = (),
        hypotheses: Iterable[Hypothesis] = (),
    ) -> None: ...


@dataclass(frozen=True)
class Agents:
    triage: Triage
    specialists: Mapping[str, Specialist]
    hypothesize: Hypothesize


AgentsFactory = Callable[[Path], Agents]


def fixture_agents(scenario: Path) -> Agents:
    """The real agents over a scenario's files, all sharing one Ollama model."""
    from tracehound.agents.dependency import DependencyAgent
    from tracehound.agents.deploy import DeployAgent
    from tracehound.agents.hypothesis import HypothesisAgent
    from tracehound.agents.inference import OllamaLLM
    from tracehound.agents.logs import LogsAgent
    from tracehound.agents.metrics import MetricsAgent
    from tracehound.agents.triage import TriageAgent
    from tracehound.tools.deploys import FileDeploySource
    from tracehound.tools.logs import FileLogSource
    from tracehound.tools.metrics import FileMetricSource
    from tracehound.tools.traces import FileTraceSource
    from tracehound.tools.triage import load_topology

    model = os.environ.get("OLLAMA_MODEL")
    llm = OllamaLLM(model) if model else OllamaLLM()
    return Agents(
        triage=TriageAgent(scenario, llm),
        specialists={
            "logs": LogsAgent(FileLogSource(scenario), llm),
            "metrics": MetricsAgent(FileMetricSource(scenario), llm),
            "deploy": DeployAgent(FileDeploySource(scenario), llm),
            "dependency": DependencyAgent(FileTraceSource(scenario), load_topology(scenario), llm),
        },
        hypothesize=HypothesisAgent(llm),
    )


def fixture_user_ids() -> frozenset[UUID]:
    """Users whose incidents run on scenario files, from comma-separated `FIXTURE_USER_IDS`."""
    raw = os.environ.get("FIXTURE_USER_IDS", "")
    return frozenset(UUID(part.strip()) for part in raw.split(",") if part.strip())


def fixture_scenario() -> Path:
    """The scenario folder fixture users investigate, from `FIXTURE_SCENARIO(S_DIR)`."""
    base = Path(os.environ.get("FIXTURE_SCENARIOS_DIR", ROOT / "scenarios"))
    return base / os.environ.get("FIXTURE_SCENARIO", DEFAULT_SCENARIO)


def _now() -> datetime:
    return datetime.now(UTC)


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


class InvestigationRunner:
    """Runs one investigation per submitted incident on a small thread pool."""

    def __init__(
        self,
        store: Store,
        *,
        fixture_users: frozenset[UUID] | None = None,
        scenario: Path | None = None,
        agents_factory: AgentsFactory = fixture_agents,
        max_workers: int | None = None,
    ) -> None:
        self._store = store
        self._fixture_users = fixture_user_ids() if fixture_users is None else fixture_users
        self._scenario = scenario or fixture_scenario()
        self._agents_factory = agents_factory
        workers = max_workers or int(os.environ.get("INVESTIGATION_WORKERS", "2"))
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="investigation")

    def submit(self, incident: IncidentRecord, user_id: UUID) -> Future[None]:
        return self._executor.submit(self.run, incident, user_id)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def run(self, incident: IncidentRecord, user_id: UUID) -> None:
        """Investigate one incident and store the outcome. Never raises."""
        try:
            self._store.start(incident.id, user_id, incident.run_id)
        except Exception:
            logger.exception("Failed to mark incident %s running", incident.id)
            return
        if user_id not in self._fixture_users:
            self._fail(incident.id, LIVE_NOT_SUPPORTED, {})
            return
        state: dict[str, Any] = {}
        try:
            self._investigate(incident, state)
        except Exception as exc:
            logger.exception("Investigation failed for incident %s", incident.id)
            self._fail(incident.id, _describe(exc), state)
            return
        try:
            self._store.complete(
                incident.id,
                state.get("scope"),
                state.get("findings", []),
                list(state.get("evidence", {}).values()),
                state.get("hypotheses", []),
            )
        except Exception:
            logger.exception("Failed to store the result of incident %s", incident.id)

    def _fail(self, incident_id: UUID, error: str, state: dict[str, Any]) -> None:
        try:
            self._store.fail(
                incident_id,
                error,
                scope=state.get("scope"),
                findings=state.get("findings", []),
                evidence=list(state.get("evidence", {}).values()),
                hypotheses=state.get("hypotheses", []),
            )
        except Exception:
            logger.exception("Failed to mark incident %s failed", incident_id)

    def _investigate(self, incident: IncidentRecord, state: dict[str, Any]) -> None:
        """Run the graph, copying each state snapshot into `state` so a failure keeps partials."""
        scenario = self._scenario
        alert = json.loads((scenario / "scenario.json").read_text())["alert"]
        # Scenario files have fixed timestamps, so investigate the scenario's own window.
        graph_incident = incident.model_copy(
            update={
                "service_id": alert["service_id"],
                "window_start": datetime.fromisoformat(alert["window_start"]),
                "window_end": datetime.fromisoformat(alert["window_end"]),
                "trace_id": alert.get("trace_id"),
            }
        )
        agents = self._agents_factory(scenario)
        graph = build_graph(
            self._tracked(incident.id, "triage", agents.triage),
            {
                name: self._tracked_specialist(incident.id, name, specialist)
                for name, specialist in agents.specialists.items()
            },
            self._tracked(incident.id, "hypothesis", agents.hypothesize),
            checkpointer=InMemorySaver(serde=SERDE),
        )
        config = {"configurable": {"thread_id": str(incident.run_id)}}
        for snapshot in graph.stream({"incident": graph_incident}, config, stream_mode="values"):
            state.update(snapshot)

    def _record(self, incident_id: UUID, agent: AgentName, run: AgentRun) -> None:
        try:
            self._store.record_agent(incident_id, agent, run)
        except Exception:
            logger.exception("Failed to record %s for incident %s", agent, incident_id)

    def _call(self, incident_id: UUID, agent: AgentName, fn: Callable[..., T], *args: Any) -> T:
        started = _now()
        self._record(incident_id, agent, AgentRun(status="running", started_at=started))
        try:
            result = fn(*args)
        except Exception as exc:
            self._record(
                incident_id,
                agent,
                AgentRun(
                    status="failed", started_at=started, finished_at=_now(), error=_describe(exc)
                ),
            )
            raise
        self._record(
            incident_id,
            agent,
            AgentRun(status="completed", started_at=started, finished_at=_now()),
        )
        return result

    def _tracked(
        self, incident_id: UUID, agent: AgentName, fn: Callable[..., T]
    ) -> Callable[..., T]:
        """Wrap triage or hypothesis: failures are recorded and still end the run."""

        def wrapped(incident: IncidentRecord, *rest: Any) -> T:
            return self._call(incident_id, agent, fn, incident, *rest)

        return wrapped

    def _tracked_specialist(
        self, incident_id: UUID, name: str, specialist: Specialist
    ) -> Specialist:
        """Wrap a specialist: a failure is recorded and yields an empty report, so the
        other specialists' results still reach the hypothesis step."""
        agent: AgentName = SpecialistName(name).value  # type: ignore[assignment]

        def wrapped(scope: InvestigationScope, run_id: UUID) -> SpecialistReport:
            try:
                return self._call(incident_id, agent, specialist, scope, run_id)
            except Exception:
                logger.exception("Specialist %s failed for run %s", name, run_id)
                return SpecialistReport(
                    specialist=SpecialistName(name),
                    summary=f"{name} specialist failed.",
                    findings=[],
                    evidence=[],
                )

        return wrapped


def get_investigation_runner(request: Request) -> InvestigationRunner:
    """Return the runner that `create_app` started on startup."""
    runner: InvestigationRunner = request.app.state.investigation_runner
    return runner


InvestigationRunnerDep = Annotated[InvestigationRunner, Depends(get_investigation_runner)]
