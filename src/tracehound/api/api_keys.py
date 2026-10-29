"""API key routes. Keys are issued to the signed-in user."""

import logging
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException, Response, status

from tracehound.api.dependencies import ApiKeyManagementDep, CurrentUserDep
from tracehound.helpers.api_key_helper import InvalidCursor
from tracehound.schemas import ApiKeyCreated, ApiKeyCreateRequest, ApiKeyPage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/api-keys", tags=["api-keys"])


@router.get("")
def list_api_keys(
    user: CurrentUserDep, keys: ApiKeyManagementDep, cursor: str | None = None
) -> ApiKeyPage:
    try:
        return keys.list(user.user_id, cursor)
    except InvalidCursor as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid pagination cursor."
        ) from exc
    except psycopg.Error as exc:
        logger.exception("Failed to list API keys for user %s", user.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not list the API keys.",
        ) from exc


@router.post("", status_code=status.HTTP_201_CREATED)
def create_api_key(
    payload: ApiKeyCreateRequest, user: CurrentUserDep, keys: ApiKeyManagementDep
) -> ApiKeyCreated:
    try:
        return keys.create(user.user_id, payload.name)
    except psycopg.Error as exc:
        logger.exception("Failed to create API key for user %s", user.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create the API key.",
        ) from exc


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(key_id: UUID, user: CurrentUserDep, keys: ApiKeyManagementDep) -> Response:
    try:
        revoked = keys.revoke(user.user_id, key_id)
    except psycopg.Error as exc:
        logger.exception("Failed to revoke API key %s for user %s", key_id, user.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not revoke the API key.",
        ) from exc
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
