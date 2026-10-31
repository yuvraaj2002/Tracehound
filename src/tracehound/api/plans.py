"""Plan routes. Public: the landing page shows pricing before anyone signs in."""

import logging

import psycopg
from fastapi import APIRouter, HTTPException, Response, status

from tracehound.api.dependencies import PlanCatalogDep
from tracehound.schemas import PlanList

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/plans", tags=["plans"])


@router.get("")
def list_plans(plans: PlanCatalogDep, response: Response) -> PlanList:
    try:
        result = plans.list()
    except psycopg.Error as exc:
        logger.exception("Failed to list plans")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not list the plans.",
        ) from exc
    # Same for every visitor and rarely changes, so browsers and CDNs may reuse it briefly.
    response.headers["Cache-Control"] = "public, max-age=300"
    return result
