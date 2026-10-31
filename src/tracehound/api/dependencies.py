"""FastAPI dependencies shared by the route modules."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg_pool import ConnectionPool

from tracehound.auth import InvalidToken, TokenVerifier, User
from tracehound.helpers.api_key_helper import ApiKeyManagement
from tracehound.helpers.incident_helper import IncidentHelper
from tracehound.helpers.integration_helper import IntegrationManagement
from tracehound.helpers.plan_helper import PlanCatalog

_bearer = HTTPBearer(auto_error=False)


def get_incident_helper(request: Request) -> IncidentHelper:
    """Return the helper that `create_app` attached to the running app."""
    helper: IncidentHelper = request.app.state.incident_helper
    return helper


def get_pool(request: Request) -> ConnectionPool:
    """Return the database pool that `create_app` opened on startup."""
    pool: ConnectionPool = request.app.state.pool
    return pool


PoolDep = Annotated[ConnectionPool, Depends(get_pool)]


def get_api_key_management(request: Request, pool: PoolDep) -> ApiKeyManagement:
    """Build the key manager for this request on the injected pool."""
    return ApiKeyManagement(pool, request.app.state.api_key_hash_secret)


def get_integration_management(request: Request, pool: PoolDep) -> IntegrationManagement:
    """Build the integration store for this request on the injected pool."""
    return IntegrationManagement(pool, request.app.state.integration_encryption_key)


def get_plan_catalog(pool: PoolDep) -> PlanCatalog:
    """Build the plan catalogue for this request on the injected pool."""
    return PlanCatalog(pool)


def get_token_verifier(request: Request) -> TokenVerifier:
    verifier: TokenVerifier = request.app.state.token_verifier
    return verifier


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
) -> User:
    """Resolve `Authorization: Bearer <Supabase access token>` to a user, or reply 401."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid access token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        return verifier.verify(credentials.credentials)
    except InvalidToken as exc:
        raise unauthorized from exc


IncidentHelperDep = Annotated[IncidentHelper, Depends(get_incident_helper)]
ApiKeyManagementDep = Annotated[ApiKeyManagement, Depends(get_api_key_management)]
IntegrationManagementDep = Annotated[IntegrationManagement, Depends(get_integration_management)]
PlanCatalogDep = Annotated[PlanCatalog, Depends(get_plan_catalog)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
