#!/usr/bin/env python3
"""Wait for an allowed GPU, then run the frozen WorldGen pilot by phase."""

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


import argparse
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
PYTHON = BASELINES_ROOT / "environments/worldgen/bin/python"
RUNNER = BASELINES_ROOT / "methods/worldgen/run.py"
DEFAULT_DATA_ROOT = BASELINES_ROOT / "work/worldgen/pilot_generated/table2"
ALLOWED_GPUS = {0, 1}
MIN_FREE_MIB = 40000


def gpu_states() -> list[dict[str, int]]:
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,memory.free,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        timeout=15,
    )
    states = []
    for line in completed.stdout.splitlines():
        index, free_mib, utilization = (int(part.strip()) for part in line.split(","))
        if index in ALLOWED_GPUS:
            states.append(
                {"index": index, "free_mib": free_mib, "utilization": utilization}
            )
    return states


def choose_gpu(states: list[dict[str, int]]) -> int | None:
    candidates = [
        state
        for state in states
        if state["index"] in ALLOWED_GPUS and state["free_mib"] >= MIN_FREE_MIB
    ]
    if not candidates:
        return None
    return max(
        candidates, key=lambda state: (state["free_mib"], -state["utilization"])
    )["index"]


def run_phase(phase: str, gpu: int, data_root: Path) -> tuple[int, str]:
    command = [
        str(PYTHON),
        str(RUNNER),
        "--phase",
        phase,
        "--domains",
        "indoor",
        "urban",
        "--gpus",
        str(gpu),
        "--workers",
        "1",
        "--pilot",
        "--data-root",
        str(data_root),
        "--min-free-gib",
        "100",
    ]
    environment = dict(os.environ)
    environment["PYTHONUNBUFFERED"] = "1"
    process = subprocess.Popen(
        command,
        cwd=BASELINES_ROOT.parent,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    lines: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="", flush=True)
        lines.append(line)
    return process.wait(), "".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    args = parser.parse_args()
    if args.interval < 5:
        raise ValueError("interval must be at least 5 seconds")
    data_root = args.data_root.resolve()
    try:
        data_root.relative_to(BASELINES_ROOT.resolve())
    except ValueError as exc:
        raise ValueError("data-root must remain below baselines/") from exc

    for phase in ("panorama", "reconstruct", "render"):
        while True:
            states = gpu_states()
            gpu = choose_gpu(states)
            stamp = datetime.now(timezone.utc).isoformat()
            state_text = ",".join(
                f"gpu{state['index']}={state['free_mib']}MiB/{state['utilization']}%"
                for state in states
            )
            if gpu is None:
                print(
                    f"WORLDGEN_PILOT_WAIT utc={stamp} phase={phase} {state_text}",
                    flush=True,
                )
                time.sleep(args.interval)
                continue
            print(
                f"WORLDGEN_PILOT_LAUNCH utc={stamp} phase={phase} gpu={gpu} {state_text}",
                flush=True,
            )
            returncode, output = run_phase(phase, gpu, data_root)
            if returncode == 0:
                break
            if "has only" in output and "require 40000 MiB" in output:
                print(
                    f"WORLDGEN_PILOT_RESOURCE_RETRY phase={phase} gpu={gpu}",
                    flush=True,
                )
                time.sleep(args.interval)
                continue
            print(
                f"WORLDGEN_PILOT_FAILED phase={phase} gpu={gpu} exit_code={returncode}",
                flush=True,
            )
            return returncode
    print("WORLDGEN_PILOT_COMPLETE tasks=20", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
