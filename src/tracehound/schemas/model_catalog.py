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


class ModelDetails(BaseModel):
    """Customer-facing facts about one model. Deliberately has no pricing.

    The fields after `provider_label` come from OpenRouter and are null when it doesn't list the
    model (`listed` is then false).
    """

    id: str
    name: str
    provider: str
    provider_label: str
    listed: bool
    description: str | None = None
    context_length: int | None = None
    max_output_tokens: int | None = None
    input_modalities: list[str] = []
    output_modalities: list[str] = []
    supports_tools: bool = False
    supports_structured_output: bool = False
    supports_reasoning: bool = False
    supports_temperature: bool = False
    supported_parameters: list[str] = []
    knowledge_cutoff: str | None = None
    released_at: str | None = None
    retires_at: str | None = None
    is_moderated: bool | None = None


class ProviderWithModels(BaseModel):
    """A provider with the full details of each of its models."""

    id: str
    label: str
    models: list[ModelDetails]


class FullModelCatalog(BaseModel):
    """Everything the model picker needs in one response: providers, models and their details."""

    providers: list[ProviderWithModels]
    default: ModelChoice
