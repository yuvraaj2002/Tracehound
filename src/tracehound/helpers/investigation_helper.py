"""Investigation result reads and writes against PostgreSQL."""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import cast, func, literal, select, update
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Session

from tracehound.db import SessionFactory
from tracehound.helpers.incident_helper import incident_record
from tracehound.models import Incident, InvestigationResultRow
from tracehound.schemas import (
    Evidence,
    Finding,
    Hypothesis,
    InvestigationScope,
)
from tracehound.schemas.investigation import (
    AgentName,
    AgentRun,
    IncidentDetail,
    IncidentState,
    InvestigationResult,
)

INTERRUPTED_ERROR = "Interrupted: the server restarted during the run."


def _dump_list(items: Sequence[BaseModel]) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in items]


def _result(row: InvestigationResultRow) -> InvestigationResult:
    return InvestigationResult.model_validate(
        {
            "incident_id": row.incident_id,
            "run_id": row.run_id,
            "scope": row.scope,
            "findings": row.findings,
            "evidence": row.evidence,
            "hypotheses": row.hypotheses,
            "agent_runs": row.agent_runs,
            "error": row.error,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
        }
    )


class InvestigationStore:
    """Stores each incident's investigation result and keeps `incidents.state` in step."""

    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    def start(self, incident_id: UUID, user_id: UUID, run_id: UUID) -> None:
        """Reset the result row for a new run and mark the incident RUNNING."""
        stmt = insert(InvestigationResultRow).values(
            incident_id=incident_id, user_id=user_id, run_id=run_id, started_at=func.now()
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[InvestigationResultRow.incident_id],
            set_={
                "run_id": stmt.excluded.run_id,
                "scope": None,
                "findings": [],
                "evidence": [],
                "hypotheses": [],
                "agent_runs": {},
                "error": None,
                "started_at": func.now(),
                "finished_at": None,
                "updated_at": func.now(),
            },
        )
        with self._sessions.begin() as session:
            session.execute(stmt)
            self._set_state(session, incident_id, IncidentState.RUNNING)

    def record_agent(self, incident_id: UUID, agent: AgentName, run: AgentRun) -> None:
        """Merge one agent's status into `agent_runs` in SQL, so parallel agents don't race."""
        entry = cast(literal({agent: run.model_dump(mode="json")}, JSONB), JSONB)
        stmt = (
            update(InvestigationResultRow)
            .where(InvestigationResultRow.incident_id == incident_id)
            .values(
                agent_runs=InvestigationResultRow.agent_runs.op("||")(entry),
                updated_at=func.now(),
            )
        )
        with self._sessions.begin() as session:
            session.execute(stmt)

    def complete(
        self,
        incident_id: UUID,
        scope: InvestigationScope | None,
        findings: list[Finding],
        evidence: list[Evidence],
        hypotheses: list[Hypothesis],
    ) -> None:
        """Store the run's output and mark the incident COMPLETED."""
        self._finish(
            incident_id, IncidentState.COMPLETED, None, scope, findings, evidence, hypotheses
        )

    def fail(
        self,
        incident_id: UUID,
        error: str,
        scope: InvestigationScope | None = None,
        findings: Sequence[Finding] = (),
        evidence: Sequence[Evidence] = (),
        hypotheses: Sequence[Hypothesis] = (),
    ) -> None:
        """Store whatever partial output exists plus the error, and mark the incident FAILED."""
        self._finish(
            incident_id, IncidentState.FAILED, error, scope, findings, evidence, hypotheses
        )

    def get(self, user_id: UUID, incident_id: UUID) -> IncidentDetail | None:
        """Return the incident and its result if `user_id` owns it, else None."""
        stmt = (
            select(Incident, InvestigationResultRow)
            .outerjoin(InvestigationResultRow, InvestigationResultRow.incident_id == Incident.id)
            .where(Incident.id == incident_id, Incident.user_id == user_id)
        )
        with self._sessions() as session:
            row = session.execute(stmt).first()
        if row is None:
            return None
        incident, result = row
        return IncidentDetail(
            incident=incident_record(incident),
            result=_result(result) if result is not None else None,
        )

    def fail_stale_runs(self) -> int:
        """Mark every incident left RUNNING by a previous process as FAILED; return how many."""
        mark_failed = (
            update(Incident)
            .where(Incident.state == IncidentState.RUNNING.value)
            .values(state=IncidentState.FAILED.value, updated_at=func.now())
            .returning(Incident.id, Incident.user_id, Incident.run_id)
        )
        with self._sessions.begin() as session:
            rows = session.execute(mark_failed).all()
            for incident_id, user_id, run_id in rows:
                stmt = insert(InvestigationResultRow).values(
                    incident_id=incident_id,
                    user_id=user_id,
                    run_id=run_id,
                    error=INTERRUPTED_ERROR,
                    finished_at=func.now(),
                )
                session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[InvestigationResultRow.incident_id],
                        set_={
                            "error": stmt.excluded.error,
                            "finished_at": func.now(),
                            "updated_at": func.now(),
                        },
                    )
                )
        return len(rows)

    def _finish(
        self,
        incident_id: UUID,
        state: IncidentState,
        error: str | None,
        scope: InvestigationScope | None,
        findings: Sequence[Finding],
        evidence: Sequence[Evidence],
        hypotheses: Sequence[Hypothesis],
    ) -> None:
        stmt = (
            update(InvestigationResultRow)
            .where(InvestigationResultRow.incident_id == incident_id)
            .values(
                scope=scope.model_dump(mode="json") if scope else None,
                findings=_dump_list(findings),
                evidence=_dump_list(sorted(evidence, key=lambda e: e.event_time)),
                hypotheses=_dump_list(hypotheses),
                error=error,
                finished_at=func.now(),
                updated_at=func.now(),
            )
        )
        with self._sessions.begin() as session:
            session.execute(stmt)
            self._set_state(session, incident_id, state)

    @staticmethod
    def _set_state(session: Session, incident_id: UUID, state: IncidentState) -> None:
        session.execute(
            update(Incident)
            .where(Incident.id == incident_id)
            .values(state=state.value, updated_at=func.now())
        )
