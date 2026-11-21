"""Shared helpers: load skill scripts as modules and run them as CLIs."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_module(relative: str):
    """Import a file under skills/ (for example 'openapi-review/scripts/openapi_lint.py')."""
    path = SKILLS / relative
    name = "skill_" + path.stem
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_script(relative: str, *args: str, env=None, stdin: bytes | None = None):
    return subprocess.run(
        [sys.executable, str(SKILLS / relative), *args],
        capture_output=True,
        input=stdin,
        env=env,
        timeout=60,
    )


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES
