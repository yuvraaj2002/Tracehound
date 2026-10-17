"""FastAPI dependencies shared by the route modules."""

from typing import Annotated

from fastapi import Depends, Request

from tracehound.helpers.incident_helper import IncidentHelper


def get_incident_helper(request: Request) -> IncidentHelper:
    """Return the helper that `create_app` attached to the running app."""
    helper: IncidentHelper = request.app.state.incident_helper
    return helper


IncidentHelperDep = Annotated[IncidentHelper, Depends(get_incident_helper)]
