"""Investigation result reads and writes against PostgreSQL."""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

from tracehound.schemas import (
    Evidence,
    Finding,
    Hypothesis,
    IncidentRecord,
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

_FINISH_SQL = """
UPDATE investigation_results
SET scope = %(scope)s, findings = %(findings)s, evidence = %(evidence)s,
    hypotheses = %(hypotheses)s, error = %(error)s, finished_at = now(), updated_at = now()
WHERE incident_id = %(incident_id)s
"""


def _dump_list(items: Sequence[BaseModel]) -> Jsonb:
    return Jsonb([item.model_dump(mode="json") for item in items])


class InvestigationStore:
    """Stores each incident's investigation result and keeps `incidents.state` in step."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def start(self, incident_id: UUID, user_id: UUID, run_id: UUID) -> None:
        """Reset the result row for a new run and mark the incident RUNNING."""
        with self._pool.connection() as conn, conn.transaction():
            conn.execute(
                "INSERT INTO investigation_results (incident_id, user_id, run_id, started_at)"
                " VALUES (%s, %s, %s, now())"
                " ON CONFLICT (incident_id) DO UPDATE SET run_id = excluded.run_id,"
                " scope = NULL, findings = '[]', evidence = '[]', hypotheses = '[]',"
                " agent_runs = '{}', error = NULL, started_at = now(), finished_at = NULL,"
                " updated_at = now()",
                (incident_id, user_id, run_id),
            )
            self._set_state(conn, incident_id, IncidentState.RUNNING)

    def record_agent(self, incident_id: UUID, agent: AgentName, run: AgentRun) -> None:
        """Merge one agent's status into `agent_runs`."""
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE investigation_results"
                " SET agent_runs = agent_runs || jsonb_build_object(%s::text, %s::jsonb),"
                " updated_at = now() WHERE incident_id = %s",
                (agent, Jsonb(run.model_dump(mode="json")), incident_id),
            )

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
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT to_jsonb(i) AS incident, to_jsonb(r) AS result"
                " FROM incidents i LEFT JOIN investigation_results r ON r.incident_id = i.id"
                " WHERE i.id = %s AND i.user_id = %s",
                (incident_id, user_id),
            ).fetchone()
        if row is None:
            return None
        result: dict[str, Any] | None = row["result"]
        return IncidentDetail(
            incident=IncidentRecord.model_validate(row["incident"]),
            result=InvestigationResult.model_validate(result) if result else None,
        )

    def fail_stale_runs(self) -> int:
        """Mark every incident left RUNNING by a previous process as FAILED; return how many."""
        with self._pool.connection() as conn, conn.transaction():
            rows = conn.execute(
                "UPDATE incidents SET state = %s, updated_at = now()"
                " WHERE state = %s RETURNING id, user_id, run_id",
                (IncidentState.FAILED.value, IncidentState.RUNNING.value),
            ).fetchall()
            for row in rows:
                conn.execute(
                    "INSERT INTO investigation_results"
                    " (incident_id, user_id, run_id, error, finished_at)"
                    " VALUES (%s, %s, %s, %s, now())"
                    " ON CONFLICT (incident_id) DO UPDATE SET error = excluded.error,"
                    " finished_at = now(), updated_at = now()",
                    (row["id"], row["user_id"], row["run_id"], INTERRUPTED_ERROR),
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
        params = {
            "incident_id": incident_id,
            "scope": Jsonb(scope.model_dump(mode="json")) if scope else None,
            "findings": _dump_list(findings),
            "evidence": _dump_list(sorted(evidence, key=lambda e: e.event_time)),
            "hypotheses": _dump_list(hypotheses),
            "error": error,
        }
        with self._pool.connection() as conn, conn.transaction():
            conn.execute(_FINISH_SQL, params)
            self._set_state(conn, incident_id, state)

    @staticmethod
    def _set_state(conn: Any, incident_id: UUID, state: IncidentState) -> None:
        conn.execute(
            "UPDATE incidents SET state = %s, updated_at = now() WHERE id = %s",
            (state.value, incident_id),
        )
