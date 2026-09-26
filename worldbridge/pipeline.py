"""WorldBridge generation entry points."""
from __future__ import annotations

import subprocess
from typing import Any

from worldbridge.paths import ROOT, runtime_environment
from worldbridge.urban.core import generate_descriptor

SCENE_SCRIPTS = {
    "nature": "scene_stream.sh",
    "indoor": "scene_stream_indoor.sh",
    "urban": "scene_stream_urban.sh",
    "object": "obj.sh",
}


def infer_descriptor(seed: int = 42, topology: str | None = None) -> dict[str, Any]:
    return generate_descriptor(seed, topology)


def generate_scene(mode: str, prompt: str) -> int:
    if not prompt.strip():
        raise ValueError("A scene prompt is required.")
    return subprocess.run(
        ["bash", str(ROOT / "scripts" / SCENE_SCRIPTS[mode]), prompt],
        cwd=ROOT,
        env=runtime_environment(),
        check=False,
    ).returncode
