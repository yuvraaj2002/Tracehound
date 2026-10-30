"""Incident intake routes. Incidents belong to the signed-in user."""

import logging
from typing import Annotated

import psycopg
from fastapi import APIRouter, HTTPException, Query, status

from tracehound.api.dependencies import CurrentUserDep, IncidentHelperDep
from tracehound.helpers.pagination import InvalidCursor
from tracehound.schemas import (
    IncidentAccepted,
    IncidentCreateRequest,
    IncidentListQuery,
    IncidentPage,
    IncidentStats,
    IncidentStatsQuery,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/incidents", tags=["incidents"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def create_incident(
    payload: IncidentCreateRequest, user: CurrentUserDep, helper: IncidentHelperDep
) -> IncidentAccepted:
    try:
        return helper.create(user.user_id, payload)
    except psycopg.Error as exc:
        logger.exception("Failed to store incident for service %s", payload.service_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not store the incident.",
        ) from exc


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
