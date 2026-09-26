#!/usr/bin/env python3
"""Run the MajutsuCity matrix with the baselines-local L40S host launcher."""

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
import os
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
RUNNER_PATH = BASELINES / "methods/majutsucity/run.py"
SPEC = importlib.util.spec_from_file_location("majutsucity_matrix_base", RUNNER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load MajutsuCity matrix runner: {RUNNER_PATH}")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
runner.ADAPTER = BASELINES / "methods/majutsucity/adapter_l40s.py"
local_python = Path("/dev/shm/worldbridge_majutsucity_l40s/majutsucity_env/bin/python")
if os.environ.get("MAJUTSUCITY_USE_RAM_STAGE") == "1" and local_python.is_file():
    runner.PYTHON = local_python


def host_run_dir(mode: str, spec_id: str, seed: int) -> Path:
    root = "pilot_l40s" if mode == "pilot" else "table2"
    return BASELINES / f"data/{root}/urban/majutsucity/{spec_id}/seed_{seed}"


runner.run_dir = host_run_dir

base_wait_for_gpus = runner.wait_for_gpus


def host_wait_for_gpus(gpus, minimum_free_mib, stable_seconds, poll_seconds):
    if minimum_free_mib <= 0:
        print(
            "MAJUTSU_GPU_GATE_DISABLED gpus=" + ",".join(str(gpu) for gpu in gpus),
            flush=True,
        )
        return
    return base_wait_for_gpus(gpus, minimum_free_mib, stable_seconds, poll_seconds)


runner.wait_for_gpus = host_wait_for_gpus


if __name__ == "__main__":
    raise SystemExit(runner.main())
