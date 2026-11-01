"""Incident intake routes. Incidents belong to the signed-in user."""

import logging
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException, Query, status

from tracehound.api.dependencies import (
    CurrentUserDep,
    IncidentHelperDep,
    IntegrationManagementDep,
    InvestigationStoreDep,
)
from tracehound.helpers.pagination import InvalidCursor
from tracehound.schemas import (
    IncidentAccepted,
    IncidentCreateRequest,
    IncidentDetail,
    IncidentListQuery,
    IncidentPage,
    IncidentRecord,
    IncidentStats,
    IncidentStatsQuery,
)
from tracehound.schemas.investigation import IncidentState
from tracehound.worker import InvestigationRunnerDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/incidents", tags=["incidents"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def create_incident(
    payload: IncidentCreateRequest,
    user: CurrentUserDep,
    helper: IncidentHelperDep,
    integrations: IntegrationManagementDep,
    runner: InvestigationRunnerDep,
) -> IncidentAccepted:
    try:
        missing = integrations.missing_signals(user.user_id)
    except psycopg.Error as exc:
        logger.exception("Failed to check integrations for service %s", payload.service_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not check the integrations.",
        ) from exc
    if missing:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail=f"Integration is not configured for: {', '.join(missing)}.",
        )
    try:
        accepted = helper.create(user.user_id, payload)
    except psycopg.Error as exc:
        logger.exception("Failed to store incident for service %s", payload.service_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not store the incident.",
        ) from exc
    now = datetime.now(UTC)
    record = IncidentRecord(
        id=accepted.incident_id,
        run_id=accepted.run_id,
        state=IncidentState.CREATED,
        created_at=now,
        updated_at=now,
        **payload.model_dump(),
    )
    try:
        runner.submit(record, user.user_id)
    except Exception:
        # The incident is stored either way; it stays CREATED and the 202 still stands.
        logger.exception("Failed to start the investigation of incident %s", record.id)
    return accepted


@router.get("")
def list_incidents(
    query: Annotated[IncidentListQuery, Query()], user: CurrentUserDep, helper: IncidentHelperDep
) -> IncidentPage:
    try:
        return helper.list(user.user_id, query)
    except InvalidCursor as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid pagination cursor."
        ) from exc
    except psycopg.Error as exc:
        logger.exception("Failed to list incidents for user %s", user.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load incidents.",
        ) from exc


# Declared before any `/{incident_id}` route so "stats" is never parsed as an id.
@router.get("/stats")
def incident_stats(
    query: Annotated[IncidentStatsQuery, Query()], user: CurrentUserDep, helper: IncidentHelperDep
) -> IncidentStats:
    try:
        return helper.stats(user.user_id, query)
    except psycopg.Error as exc:
        logger.exception("Failed to compute incident stats for user %s", user.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load incident stats.",
        ) from exc


@router.get("/{incident_id}")
def get_incident(
    incident_id: UUID, user: CurrentUserDep, store: InvestigationStoreDep
) -> IncidentDetail:
    try:
        detail = store.get(user.user_id, incident_id)
    except psycopg.Error as exc:
        logger.exception("Failed to load incident %s", incident_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load the incident.",
        ) from exc
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found.")
    return detail
