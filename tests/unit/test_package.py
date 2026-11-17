import importlib

import tracehound


def test_version_is_exposed() -> None:
    assert tracehound.__version__ == "0.1.0"


def test_subpackages_import() -> None:
    for name in ("schemas", "tools", "agents", "orchestrator", "db", "helpers", "api"):
        importlib.import_module(f"tracehound.{name}")
