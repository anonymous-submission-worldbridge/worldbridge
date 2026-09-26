#!/usr/bin/env python3
"""Run a disjoint MajutsuCity Table-2 shard on physical GPUs 5, 6 and 7."""

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
LAUNCHER_PATH = BASELINES / "methods/majutsucity/run_4090_matrix.py"
SPEC = importlib.util.spec_from_file_location(
    "majutsucity_4090_primary_matrix", LAUNCHER_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load MajutsuCity current-host matrix: {LAUNCHER_PATH}")
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)
launcher.runner.ADAPTER = BASELINES / "methods/majutsucity/adapter_4090_b.py"


if __name__ == "__main__":
    raise SystemExit(launcher.runner.main())
