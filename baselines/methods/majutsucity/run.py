#!/usr/bin/env python3
"""Run the preregistered MajutsuCity pilot or formal Urban matrix."""

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
import json
import subprocess
import time
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
ADAPTER = BASELINES / "methods/majutsucity/adapter.py"
PYTHON = BASELINES / "envs/majutsucity/bin/python"
SPEC_FILE = BASELINES / "protocol/generation/urban_specs.jsonl"
PILOT_INDICES = {0, 6, 12, 18, 24}


def load_specs(pilot: bool) -> list[dict]:
    specs = [
        json.loads(line)
        for line in SPEC_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if pilot:
        specs = [spec for spec in specs if int(spec["spec_index"]) in PILOT_INDICES]
    return specs


def free_memory() -> dict[int, int]:
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,memory.free",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip())
    result = {}
    for line in completed.stdout.splitlines():
        index, free = [part.strip() for part in line.split(",", 1)]
        result[int(index)] = int(free)
    return result


def wait_for_gpus(
    gpus: list[int],
    minimum_free_mib: int,
    stable_seconds: float,
    poll_seconds: float,
) -> None:
    if stable_seconds < 0:
        raise ValueError("stable_seconds must be non-negative")
    if poll_seconds <= 0:
        raise ValueError("poll_seconds must be positive")
    idle_since: float | None = None
    while True:
        observed = free_memory()
        missing = [gpu for gpu in gpus if observed.get(gpu, 0) < minimum_free_mib]
        now = time.monotonic()
        if missing:
            idle_since = None
            print(
                "MAJUTSU_GPU_GATE_WAIT "
                + " ".join(
                    f"gpu={gpu}:free={observed.get(gpu, 0)}MiB" for gpu in missing
                ),
                flush=True,
            )
        else:
            if idle_since is None:
                idle_since = now
            held_seconds = now - idle_since
            if held_seconds >= stable_seconds:
                print(
                    "MAJUTSU_GPU_GATE_PASS "
                    + " ".join(f"gpu={gpu}:free={observed[gpu]}MiB" for gpu in gpus)
                    + f" stable={held_seconds:.1f}s",
                    flush=True,
                )
                return
            print(
                "MAJUTSU_GPU_GATE_STABILIZING "
                + " ".join(f"gpu={gpu}:free={observed[gpu]}MiB" for gpu in gpus)
                + f" stable={held_seconds:.1f}/{stable_seconds:.1f}s",
                flush=True,
            )
        time.sleep(poll_seconds)


def run_dir(mode: str, spec_id: str, seed: int) -> Path:
    root = "pilot" if mode == "pilot" else "table2"
    return BASELINES / f"data/{root}/urban/majutsucity/{spec_id}/seed_{seed}"


def terminal_quality_failure(destination: Path) -> bool:
    """An exit-0 renderer with a failed frozen validator is not retried."""
    render_path = destination / "render_command.json"
    validation_path = destination / "renders/validation.json"
    if not render_path.is_file() or not validation_path.is_file():
        return False
    try:
        render = json.loads(render_path.read_text(encoding="utf-8"))
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return (
        render.get("exit_code") == 0
        and render.get("validation_valid") is False
        and validation.get("valid") is False
        and "finished_at" in render
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial-mode", choices=("pilot", "formal"), required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=None)
    parser.add_argument("--render-gpu", type=int, default=4)
    parser.add_argument("--layout-gpu", type=int, default=1)
    parser.add_argument("--pipeline-gpus", type=int, nargs="+", default=[1, 4])
    parser.add_argument(
        "--minimum-free-mib",
        type=int,
        default=47000,
        help=(
            "Optional controller-level GPU threshold. CUDA stages additionally "
            "enforce their frozen just-in-time 47000 MiB gates."
        ),
    )
    parser.add_argument("--stable-gpu-seconds", type=float, default=300.0)
    parser.add_argument("--gpu-poll-seconds", type=float, default=10.0)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--only-spec", action="append", default=[])
    args = parser.parse_args()
    pilot = args.trial_mode == "pilot"
    seeds = (
        args.seeds if args.seeds is not None else ([0, 1] if pilot else [0, 1, 2, 3])
    )
    if any(seed not in range(4) for seed in seeds):
        parser.error("seeds must be selected from 0,1,2,3")
    specs = load_specs(pilot)
    if args.only_spec:
        specs = [spec for spec in specs if spec["spec_id"] in set(args.only_spec)]
    expected = len(specs) * len(seeds)
    completed_count = 0
    failed = []
    for spec in specs:
        for seed in seeds:
            destination = run_dir(args.trial_mode, spec["spec_id"], seed)
            if (destination / "SUCCESS").is_file():
                completed_count += 1
                print(f"MAJUTSU_SKIP {spec['spec_id']} seed={seed}", flush=True)
                continue
            if terminal_quality_failure(destination):
                failed.append(
                    {
                        "spec_id": spec["spec_id"],
                        "seed": seed,
                        "reason": "quality_failure",
                    }
                )
                print(
                    f"MAJUTSU_QUALITY_TERMINAL {spec['spec_id']} seed={seed}",
                    flush=True,
                )
                continue
            return_code = 1
            for attempt in range(1, args.attempts + 1):
                wait_for_gpus(
                    args.pipeline_gpus,
                    args.minimum_free_mib,
                    args.stable_gpu_seconds,
                    args.gpu_poll_seconds,
                )
                command = [
                    str(PYTHON),
                    str(ADAPTER),
                    "--trial-mode",
                    args.trial_mode,
                    "--spec-id",
                    spec["spec_id"],
                    "--seed",
                    str(seed),
                    "--gpu",
                    str(args.render_gpu),
                    "--layout-gpu",
                    str(args.layout_gpu),
                    "--stage",
                    "all",
                ]
                print(
                    f"MAJUTSU_START {spec['spec_id']} seed={seed} attempt={attempt}",
                    flush=True,
                )
                completed = subprocess.run(command, cwd=BASELINES.parent, check=False)
                return_code = completed.returncode
                if return_code == 0 and (destination / "SUCCESS").is_file():
                    break
                if terminal_quality_failure(destination):
                    print(
                        f"MAJUTSU_QUALITY_TERMINAL {spec['spec_id']} seed={seed}",
                        flush=True,
                    )
                    break
                print(
                    f"MAJUTSU_RETRY {spec['spec_id']} seed={seed} "
                    f"attempt={attempt} exit={return_code}",
                    flush=True,
                )
            if return_code == 0 and (destination / "SUCCESS").is_file():
                completed_count += 1
                print(f"MAJUTSU_OK {spec['spec_id']} seed={seed}", flush=True)
            else:
                failed.append(
                    {
                        "spec_id": spec["spec_id"],
                        "seed": seed,
                        "exit": return_code,
                        "reason": "quality_failure"
                        if terminal_quality_failure(destination)
                        else "infrastructure_failed",
                    }
                )
                print(
                    f"MAJUTSU_TERMINAL_FAIL {spec['spec_id']} seed={seed}", flush=True
                )
    print(
        f"MAJUTSU_MATRIX_COMPLETE success={completed_count}/{expected} failed={len(failed)}",
        flush=True,
    )
    if failed:
        print(json.dumps(failed, indent=2), flush=True)
    return 0 if not failed and completed_count == expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
