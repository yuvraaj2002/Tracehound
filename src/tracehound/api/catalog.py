"""Service catalog routes: the signed-in user's Backstage catalog-info.yaml."""

import logging

import psycopg
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool

from tracehound.api.dependencies import CatalogStoreDep, CurrentUserDep
from tracehound.helpers.catalog_helper import MAX_CATALOG_BYTES, CatalogInvalid, parse_catalog
from tracehound.schemas.catalog import CatalogSummary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/catalog", tags=["catalog"])

_YAML_BODY = {
    "requestBody": {
        "required": True,
        "description": "A Backstage catalog-info.yaml, as is. Separate entities with ---.",
        "content": {"application/yaml": {"schema": {"type": "string"}}},
    }
}


@router.get("")
def get_catalog(user: CurrentUserDep, catalogs: CatalogStoreDep) -> CatalogSummary:
    try:
        catalog = catalogs.get(user.user_id)
    except psycopg.Error as exc:
        logger.exception("Failed to read the catalog for user %s", user.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load the catalog.",
        ) from exc
    if catalog is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No catalog uploaded.")
    return catalog


@router.put("", openapi_extra=_YAML_BODY)
async def put_catalog(
    request: Request, user: CurrentUserDep, catalogs: CatalogStoreDep
) -> CatalogSummary:
    """Replace the catalog with the request body.

    Every problem is reported at once in a 422, with ``detail`` as a list of messages.
    """
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_CATALOG_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="The catalog is over 1 MB."
        )
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_CATALOG_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="The catalog is over 1 MB."
            )
    try:
        source = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=["the catalog must be UTF-8 text"],
        ) from exc
    try:
        catalog = await run_in_threadpool(parse_catalog, source)
    except CatalogInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.problems
        ) from exc
    try:
        return await run_in_threadpool(catalogs.put, user.user_id, source, catalog)
    except psycopg.Error as exc:
        logger.exception("Failed to save the catalog for user %s", user.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save the catalog.",
        ) from exc
