"""Contracts for the models Tracehound offers, loaded from `resources/config.json`."""

from pydantic import BaseModel


class ModelProviderInfo(BaseModel):
    """A provider and the model ids it offers (OpenRouter ids, e.g. `nvidia/...:free`)."""

    id: str
    label: str
    models: list[str]


class ModelChoice(BaseModel):
    provider: str
    model: str


class ModelCatalog(BaseModel):
    """Every model that can be assigned to an agent, plus the default for unconfigured agents."""

    providers: list[ModelProviderInfo]
    default: ModelChoice
