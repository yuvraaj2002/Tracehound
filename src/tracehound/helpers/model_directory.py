"""Customer-facing details for the configured models, from OpenRouter's public list."""

import re
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime

import httpx

from tracehound.helpers.model_config_helper import load_model_config
from tracehound.schemas import FullModelCatalog, ModelDetails, ProviderWithModels

MODELS_URL = "https://openrouter.ai/api/v1/models"
CACHE_SECONDS = 3600


class ModelDirectoryUnavailable(Exception):
    """OpenRouter could not be reached or answered badly."""


def fetch_openrouter_models() -> list[dict]:
    try:
        response = httpx.get(MODELS_URL, timeout=10.0)
        response.raise_for_status()
        return list(response.json()["data"])
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise ModelDirectoryUnavailable(str(exc)) from exc


def _display_name(name: str) -> str:
    """OpenRouter names look like `Google: Gemma 4 26B A4B (free)`; keep just the model."""
    name = re.sub(r"\s*\(free\)\s*$", "", name)
    return name.split(": ", 1)[-1].strip()


def _date(timestamp: int | float | None) -> str | None:
    return datetime.fromtimestamp(timestamp, UTC).date().isoformat() if timestamp else None


class ModelDirectory:
    """Details for the models in `config.json`. The OpenRouter list is cached for an hour."""

    def __init__(self, fetch: Callable[[], list[dict]] = fetch_openrouter_models) -> None:
        self._fetch = fetch
        self._lock = threading.Lock()
        self._cached: dict[str, dict] = {}
        self._fetched_at = 0.0

    def _listing(self) -> dict[str, dict]:
        with self._lock:
            if not self._cached or time.monotonic() - self._fetched_at > CACHE_SECONDS:
                self._cached = {model["id"]: model for model in self._fetch()}
                self._fetched_at = time.monotonic()
            return self._cached

    def details(self, model_id: str) -> ModelDetails | None:
        """Details for a configured model, or None when it isn't one of ours."""
        provider = next(
            (p for p in load_model_config()["providers"] if model_id in p["models"]), None
        )
        if provider is None:
            return None
        base = {
            "id": model_id,
            "provider": provider["id"],
            "provider_label": provider["label"],
        }
        # Our own wording wins: OpenRouter cuts its descriptions off mid-sentence.
        written = load_model_config().get("descriptions", {}).get(model_id)
        raw = self._listing().get(model_id)
        if raw is None:
            return ModelDetails(
                **base,
                name=model_id.split("/", 1)[1].removesuffix(":free"),
                listed=False,
                description=written,
            )
        params = raw.get("supported_parameters") or []
        architecture = raw.get("architecture") or {}
        top = raw.get("top_provider") or {}
        return ModelDetails(
            **base,
            name=_display_name(raw.get("name") or model_id),
            listed=True,
            description=written or raw.get("description"),
            context_length=raw.get("context_length"),
            max_output_tokens=top.get("max_completion_tokens"),
            input_modalities=architecture.get("input_modalities") or [],
            output_modalities=architecture.get("output_modalities") or [],
            supports_tools="tools" in params,
            supports_structured_output="structured_outputs" in params
            or "response_format" in params,
            supports_reasoning="reasoning" in params or bool(raw.get("reasoning")),
            supports_temperature="temperature" in params,
            supported_parameters=sorted(params),
            knowledge_cutoff=raw.get("knowledge_cutoff"),
            released_at=_date(raw.get("created")),
            retires_at=raw.get("expiration_date"),
            is_moderated=top.get("is_moderated"),
        )

    def catalog(self) -> FullModelCatalog:
        """Every provider with the details of all its models: what the model picker needs."""
        config = load_model_config()
        providers = [
            ProviderWithModels(
                id=provider["id"],
                label=provider["label"],
                models=[d for m in provider["models"] if (d := self.details(m)) is not None],
            )
            for provider in config["providers"]
        ]
        return FullModelCatalog(providers=providers, default=config["default"])


_directory = ModelDirectory()


def get_model_directory() -> ModelDirectory:
    return _directory
