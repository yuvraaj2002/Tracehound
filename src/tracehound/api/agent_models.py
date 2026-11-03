"""Per-agent model settings. Signed-in only: the models on offer and the facts about each."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError

from tracehound.api.dependencies import AgentModelStoreDep, CurrentUserDep
from tracehound.helpers.agent_model_helper import InvalidModelChoice
from tracehound.helpers.model_config_helper import load_model_config
from tracehound.helpers.model_directory import (
    ModelDirectory,
    ModelDirectoryUnavailable,
    get_model_directory,
)
from tracehound.schemas import (
    AgentId,
    AgentModelChoice,
    AgentModelPreferences,
    FullModelCatalog,
    ModelCatalog,
    ModelDetails,
)

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


@router.get("/preferences")
async def get_preferences(user: CurrentUserDep, store: AgentModelStoreDep) -> AgentModelPreferences:
    """The model each agent runs on for this user: their choice, or the default."""
    try:
        return await run_in_threadpool(store.get, user.user_id)
    except SQLAlchemyError as exc:
        logger.exception("Failed to read model preferences for user %s", user.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load your model settings.",
        ) from exc


@router.put("/preferences/{agent}")
async def put_preference(
    agent: AgentId, choice: AgentModelChoice, user: CurrentUserDep, store: AgentModelStoreDep
) -> AgentModelPreferences:
    """Set the model one agent runs on. Other agents keep their current choice.

    The model must be one of the catalog's, and the provider must be the one that offers it.
    """
    try:
        return await run_in_threadpool(store.put, user.user_id, agent, choice)
    except InvalidModelChoice as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception("Failed to save model preferences for user %s", user.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save your model settings.",
        ) from exc
