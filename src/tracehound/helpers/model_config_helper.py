"""Loads the allowed models from `resources/config.json`: the only models Tracehound may use."""

import json
from functools import cache
from importlib.resources import files


@cache
def load_model_config() -> dict:
    """The parsed config: `gateway`, `providers` (id, label, models) and the `default` choice."""
    return json.loads(files("tracehound.resources").joinpath("config.json").read_text())


def allowed_models() -> list[str]:
    """Every model id from every provider, in config order."""
    return [model for provider in load_model_config()["providers"] for model in provider["models"]]
