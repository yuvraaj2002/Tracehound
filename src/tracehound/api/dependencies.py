"""FastAPI dependencies shared by the route modules."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from tracehound.auth import InvalidToken, TokenVerifier, User
from tracehound.db import SessionFactory
from tracehound.helpers.api_key_helper import ApiKeyManagement
from tracehound.helpers.catalog_helper import CatalogStore
from tracehound.helpers.incident_helper import IncidentHelper
from tracehound.helpers.integration_helper import IntegrationManagement
from tracehound.helpers.investigation_helper import InvestigationStore
from tracehound.helpers.plan_helper import PlanCatalog

_bearer = HTTPBearer(auto_error=False)


def get_incident_helper(request: Request) -> IncidentHelper:
    """Return the helper that `create_app` attached to the running app."""
    helper: IncidentHelper = request.app.state.incident_helper
    return helper


def get_sessions(request: Request) -> SessionFactory:
    """Return the session factory that `create_app` built on startup."""
    sessions: SessionFactory = request.app.state.sessions
    return sessions


SessionsDep = Annotated[SessionFactory, Depends(get_sessions)]


def get_api_key_management(request: Request, sessions: SessionsDep) -> ApiKeyManagement:
    """Build the key manager for this request on the injected sessions."""
    return ApiKeyManagement(sessions, request.app.state.api_key_hash_secret)


def get_integration_management(request: Request, sessions: SessionsDep) -> IntegrationManagement:
    """Build the integration store for this request on the injected sessions."""
    return IntegrationManagement(sessions, request.app.state.integration_encryption_key)


def get_investigation_store(sessions: SessionsDep) -> InvestigationStore:
    """Build the investigation result store for this request on the injected sessions."""
    return InvestigationStore(sessions)


def get_catalog_store(sessions: SessionsDep) -> CatalogStore:
    """Build the service catalog store for this request on the injected sessions."""
    return CatalogStore(sessions)


def get_plan_catalog(sessions: SessionsDep) -> PlanCatalog:
    """Build the plan catalogue for this request on the injected sessions."""
    return PlanCatalog(sessions)


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
InvestigationStoreDep = Annotated[InvestigationStore, Depends(get_investigation_store)]
PlanCatalogDep = Annotated[PlanCatalog, Depends(get_plan_catalog)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
CatalogStoreDep = Annotated[CatalogStore, Depends(get_catalog_store)]
