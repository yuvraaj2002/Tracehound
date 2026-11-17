"""Integration routes: connect the signed-in user's telemetry backends."""

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError

from tracehound.api.dependencies import CurrentUserDep, IntegrationManagementDep
from tracehound.helpers.integration_client import test_connection
from tracehound.helpers.integration_helper import IntegrationExists, UnsupportedConfigField
from tracehound.schemas import (
    IntegrationCreateRequest,
    IntegrationList,
    IntegrationSummary,
    IntegrationUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/integrations", tags=["integrations"])


@router.get("")
def list_integrations(
    user: CurrentUserDep, integrations: IntegrationManagementDep
) -> IntegrationList:
    try:
        return integrations.list(user.user_id)
    except SQLAlchemyError as exc:
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
    except SQLAlchemyError as exc:
        logger.exception("Failed to create %s integration for user %s", payload.kind, user.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save the integration.",
        ) from exc


@router.patch("/{integration_id}")
def update_integration(
    integration_id: UUID,
    payload: IntegrationUpdateRequest,
    user: CurrentUserDep,
    integrations: IntegrationManagementDep,
) -> IntegrationSummary:
    try:
        updated = integrations.update(user.user_id, integration_id, payload)
    except UnsupportedConfigField as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"This integration has no such setting: {exc}.",
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception(
            "Failed to update integration %s for user %s", integration_id, user.user_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update the integration.",
        ) from exc
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found.")
    return updated


@router.post("/{integration_id}/test")
def test_integration(
    integration_id: UUID, user: CurrentUserDep, integrations: IntegrationManagementDep
) -> IntegrationSummary:
    """Make one authenticated read against the backend and store the outcome.

    A failed connection is a normal result (status `failing` with `last_error`), not an error
    response; only a missing integration or a database failure is.
    """
    try:
        connection = integrations.connection(user.user_id, integration_id)
        if connection is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found."
            )
        error = test_connection(connection)
        tested = integrations.record_test(user.user_id, integration_id, error)
    except SQLAlchemyError as exc:
        logger.exception("Failed to test integration %s for user %s", integration_id, user.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not test the integration.",
        ) from exc
    if tested is None:  # deleted while the test ran
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found.")
    return tested


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_integration(
    integration_id: UUID, user: CurrentUserDep, integrations: IntegrationManagementDep
) -> Response:
    try:
        deleted = integrations.delete(user.user_id, integration_id)
    except SQLAlchemyError as exc:
        logger.exception(
            "Failed to delete integration %s for user %s", integration_id, user.user_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete the integration.",
        ) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
