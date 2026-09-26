"""Portable project, dependency, model, and executable locations."""
from __future__ import annotations

import os
import site
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def path_variables() -> dict[str, str]:
    """Environment overrides affect paths only, never generation parameters."""
    defaults = {
        "WORLDBRIDGE_ROOT": str(ROOT),
        "WORLDBRIDGE_EXTERNAL": str(ROOT / "external"),
        "WORLDBRIDGE_MODELS": str(ROOT / "models"),
        "WORLDBRIDGE_CACHE": str(ROOT / ".cache"),
        "WORLDBRIDGE_PYTHON": sys.executable,
        "WORLDBRIDGE_SITE_PACKAGES": site.getsitepackages()[0],
        "BLENDER_BIN": "blender",
        "BLENDER_RESOURCES": str(ROOT / "external/blender/resources"),
    }
    return {name: os.environ.get(name, value) for name, value in defaults.items()}


def expand_paths(text: str) -> str:
    """Expand explicit path placeholders, including paths in generated scripts."""
    for name, value in path_variables().items():
        text = text.replace("${" + name + "}", value)
    return text


def runtime_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name, value in path_variables().items():
        environment.setdefault(name, value)
    roots = [str(ROOT), str(ROOT / "infinigen")]
    if environment.get("PYTHONPATH"):
        roots.append(environment["PYTHONPATH"])
    environment["PYTHONPATH"] = os.pathsep.join(roots)
    return environment
