"""Incident intake routes."""

import logging
import sqlite3

from fastapi import APIRouter, HTTPException, status

from tracehound.api.dependencies import IncidentHelperDep
from tracehound.schemas import IncidentAccepted, IncidentCreateRequest, IncidentRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/incidents", tags=["incidents"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def create_incident(payload: IncidentCreateRequest, helper: IncidentHelperDep) -> IncidentAccepted:
    try:
        return helper.create(payload)
    except sqlite3.Error as exc:
        logger.exception("Failed to store incident for service %s", payload.service_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not store the incident.",
        ) from exc


@router.get("")
def list_incidents(helper: IncidentHelperDep) -> list[IncidentRecord]:
    try:
        return helper.list_all()
    except sqlite3.Error as exc:
        logger.exception("Failed to list incidents")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load incidents.",
        ) from exc
