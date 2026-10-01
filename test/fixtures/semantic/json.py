# This file shadows stdlib json if the provider drops Python isolated mode.
from pathlib import Path

Path("PYTHON_SOURCE_RAN").write_text("unexpected execution")


def repository_json() -> str:
    return "fixture"
