"""Locate independent baseline adapters without importing their dependencies."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
ADAPTERS = {
    "syncity": "methods/syncity/adapter.py",
    "worldgen": "methods/worldgen/adapter.py",
    "hyworld": "methods/hyworld/adapter.py",
    "gemini": "methods/gemini/adapter.py",
    "glm": "methods/glm/adapter.py",
    "glm_flash": "methods/glm_flash/adapter.py",
    "gpt": "methods/gpt/adapter.py",
    "gpt_low": "methods/gpt/adapter_low.py",
    "gpt_medium": "methods/gpt/adapter_medium.py",
    "gpt_xhigh": "methods/gpt/adapter_xhigh.py",
    "infinigen": "methods/infinigen/adapter.py",
    "sceneweaver": "methods/sceneweaver/adapter.py",
    "spatialgen": "methods/spatialgen/adapter.py",
    "metaurban": "methods/metaurban/adapter.py",
    "majutsucity": "methods/majutsucity/adapter.py",
}


def adapter_path(method: str) -> Path:
    return ROOT / ADAPTERS[method]
