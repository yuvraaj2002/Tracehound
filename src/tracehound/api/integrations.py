"""Integration routes: connect the signed-in user's telemetry backends (Loki first)."""

import logging

import psycopg
from fastapi import APIRouter, HTTPException, status

from tracehound.api.dependencies import CurrentUserDep, IntegrationManagementDep
from tracehound.helpers.integration_helper import IntegrationExists
from tracehound.schemas import IntegrationCreateRequest, IntegrationList, IntegrationSummary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/integrations", tags=["integrations"])


@router.get("")
def list_integrations(
    user: CurrentUserDep, integrations: IntegrationManagementDep
) -> IntegrationList:
    try:
        return integrations.list(user.user_id)
    except psycopg.Error as exc:
        logger.exception("Failed to list integrations for user %s", user.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not list the integrations.",
        ) from exc


@router.post("", status_code=status.HTTP_201_CREATED)
def create_integration(
    payload: IntegrationCreateRequest, user: CurrentUserDep, integrations: IntegrationManagementDep
) -> IntegrationSummary:
    try:
        return integrations.create(user.user_id, payload)
    except IntegrationExists as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A {payload.kind} integration already exists.",
        ) from exc
    except psycopg.Error as exc:
        logger.exception("Failed to create %s integration for user %s", payload.kind, user.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save the integration.",
        ) from exc
