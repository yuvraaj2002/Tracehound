"""Incident intake routes."""

from fastapi import APIRouter, Request, status

from tracehound.schemas import IncidentAccepted, IncidentCreateRequest
from tracehound.store import IncidentStore

router = APIRouter(prefix="/v1/incidents", tags=["incidents"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def create_incident(payload: IncidentCreateRequest, request: Request) -> IncidentAccepted:
    store: IncidentStore = request.app.state.incident_store
    return store.create(payload)
