"""Per-agent model settings. Signed-in only: the models on offer and the facts about each."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from tracehound.api.dependencies import CurrentUserDep
from tracehound.helpers.model_config_helper import load_model_config
from tracehound.helpers.model_directory import (
    ModelDirectory,
    ModelDirectoryUnavailable,
    get_model_directory,
)
from tracehound.schemas import FullModelCatalog, ModelCatalog, ModelDetails

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/agent-models", tags=["agent-models"])


@router.get("/providers")
def list_model_providers(_user: CurrentUserDep) -> ModelCatalog:
    return ModelCatalog.model_validate(load_model_config())


@router.get("/catalog")
def get_model_catalog(
    _user: CurrentUserDep,
    directory: Annotated[ModelDirectory, Depends(get_model_directory)],
) -> FullModelCatalog:
    """Every provider and model with its full details, in one response (no pricing)."""
    try:
        return directory.catalog()
    except ModelDirectoryUnavailable as exc:
        logger.exception("Could not load model details")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Model details are unavailable."
        ) from exc


@router.get("/models/{model_id:path}")
def get_model_details(
    model_id: str,
    _user: CurrentUserDep,
    directory: Annotated[ModelDirectory, Depends(get_model_directory)],
) -> ModelDetails:
    """Customer-facing details for one model, e.g. `/models/google/gemma-4-26b-a4b-it:free`."""
    try:
        details = directory.details(model_id)
    except ModelDirectoryUnavailable as exc:
        logger.exception("Could not load model details")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Model details are unavailable."
        ) from exc
    if details is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown model.")
    return details
