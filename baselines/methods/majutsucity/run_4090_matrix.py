#!/usr/bin/env python3
"""Run the MajutsuCity Table-2 matrix on the current eight-card 4090 host."""

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
import shutil
import time
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
RUNNER_PATH = BASELINES / "methods/majutsucity/run.py"
SPEC = importlib.util.spec_from_file_location("majutsucity_matrix_base", RUNNER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load MajutsuCity matrix runner: {RUNNER_PATH}")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
runner.ADAPTER = BASELINES / "methods/majutsucity/adapter_4090.py"
runner.PYTHON = BASELINES / "envs/majutsucity/bin/python"


def host_run_dir(mode: str, spec_id: str, seed: int) -> Path:
    root = "pilot_l40s" if mode == "pilot" else "table2"
    return BASELINES / f"data/{root}/urban/majutsucity/{spec_id}/seed_{seed}"


runner.run_dir = host_run_dir


base_wait_for_gpus = runner.wait_for_gpus
MINIMUM_HOST_DISK_GIB = 50.0


def wait_for_disk(poll_seconds: float = 30.0) -> None:
    """Pause *before* a new scene when unrelated jobs consume /data space."""
    while True:
        free_gib = shutil.disk_usage(BASELINES).free / 1024**3
        if free_gib >= MINIMUM_HOST_DISK_GIB:
            print(f"MAJUTSU_DISK_GATE_PASS free={free_gib:.1f}GiB", flush=True)
            return
        print(
            f"MAJUTSU_DISK_GATE_WAIT free={free_gib:.1f}GiB "
            f"required={MINIMUM_HOST_DISK_GIB:.1f}GiB",
            flush=True,
        )
        time.sleep(poll_seconds)


def wait_for_host_resources(gpus, minimum_free_mib, stable_seconds, poll_seconds):
    while True:
        wait_for_disk()
        base_wait_for_gpus(gpus, minimum_free_mib, stable_seconds, poll_seconds)
        if shutil.disk_usage(BASELINES).free / 1024**3 >= MINIMUM_HOST_DISK_GIB:
            return
        print("MAJUTSU_DISK_GATE_RECHECK_WAIT", flush=True)


runner.wait_for_gpus = wait_for_host_resources


RESUME_CASE = "table2_formal_urban_residential_four_way_00_seed_1"


def previous_scene_active() -> bool:
    """Prevent the matrix from duplicating the already-running seed_1."""
    self_pid = os.getpid()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal() or int(entry.name) == self_pid:
            continue
        try:
            arguments = (entry / "cmdline").read_bytes().split(b"\0")
        except (OSError, PermissionError):
            continue
        if not arguments:
            continue
        executable = arguments[0]
        if b"methods/majutsucity/adapter_4090.py" in b" ".join(arguments):
            if (
                b"urban_residential_four_way_00" in arguments
                and b"--seed" in arguments
                and b"1" in arguments
            ):
                return True
        if RESUME_CASE.encode() in b" ".join(arguments) and any(
            token in executable for token in (b"python", b"blender")
        ):
            return True
    return False


def wait_for_previous_scene() -> None:
    destination = host_run_dir("formal", "urban_residential_four_way_00", 1)
    idle_checks = 0
    while not (
        destination / "SUCCESS"
    ).is_file() and not runner.terminal_quality_failure(destination):
        if previous_scene_active():
            idle_checks = 0
        else:
            idle_checks += 1
            if idle_checks >= 3:
                return
        print(f"MAJUTSU_WAIT_EXISTING_SEED_1 active={idle_checks == 0}", flush=True)
        time.sleep(15)


if __name__ == "__main__":
    wait_for_previous_scene()
    raise SystemExit(runner.main())
