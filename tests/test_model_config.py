from tracehound.helpers.model_config_helper import allowed_models, load_model_config


def test_default_is_an_allowed_model() -> None:
    config = load_model_config()
    assert config["default"]["model"] in allowed_models()


def test_models_are_prefixed_with_their_provider() -> None:
    for provider in load_model_config()["providers"]:
        assert all(model.startswith(f"{provider['id']}/") for model in provider["models"])
