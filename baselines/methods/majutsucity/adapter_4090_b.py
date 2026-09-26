#!/usr/bin/env python3
"""Second disjoint current-host launcher for the frozen MajutsuCity adapter."""

from __future__ import annotations

# Resolve the checkout independently of this method package's depth.
import sys as _baseline_sys
from pathlib import Path as _BaselinePath

_BASELINE_PROJECT_ROOT = next(
    p
    for p in _BaselinePath(__file__).resolve().parents
    if (p / "worldbridge").is_dir() and (p / "baselines/registry.py").is_file()
)
if str(_BASELINE_PROJECT_ROOT) not in _baseline_sys.path:
    _baseline_sys.path.insert(0, str(_BASELINE_PROJECT_ROOT))


import importlib.util
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
LAUNCHER_PATH = Path(__file__).with_name("adapter_4090.py")
SPEC = importlib.util.spec_from_file_location("majutsucity_4090_primary", LAUNCHER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(
        f"Cannot load MajutsuCity current-host launcher: {LAUNCHER_PATH}"
    )
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)

# Only the physical execution resources differ from the primary launcher. Both
# launchers share the frozen model files, source, protocol, native root, formal
# output root, seeds, prompts, inference parameters, renderer, and validators.
launcher.adapter.CONFIG_FILE = (
    BASELINES
    / "methods/majutsucity/protocol/generation/majutsucity_4090_b.paths.local.yaml"
)


if __name__ == "__main__":
    parsed = launcher.adapter.parse_args()
    if parsed.minimum_free_gib == 200.0:
        parsed.minimum_free_gib = 20.0
    result = launcher.adapter.execute(parsed)
    if result == 0 and parsed.stage == "all":
        launcher.cleanup_successful_run(parsed)
    raise SystemExit(result)
