"""Per-agent model settings. Signed-in only; starts with the catalog of models on offer."""

from fastapi import APIRouter

from tracehound.api.dependencies import CurrentUserDep
from tracehound.helpers.model_config_helper import load_model_config
from tracehound.schemas import ModelCatalog

router = APIRouter(prefix="/v1/agent-models", tags=["agent-models"])


@router.get("/providers")
def list_model_providers(_user: CurrentUserDep) -> ModelCatalog:
    return ModelCatalog.model_validate(load_model_config())
