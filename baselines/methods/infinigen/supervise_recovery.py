#!/usr/bin/env python3
"""Wait for active runs, then launch an explicit Infinigen recovery queue."""

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
import sys
import time
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
RUN_ROOT = BASELINES / "data/table2/indoor/infinigen_indoors"
TASKLIST_RUNNER = BASELINES / "methods/infinigen/run_tasklist.py"


def parse_wait(value: str) -> tuple[str, int, int, int]:
    try:
        spec_id, seed_text, gen_text, render_text = value.rsplit(":", 3)
        return spec_id, int(seed_text), int(gen_text), int(render_text)
    except (ValueError, TypeError) as error:
        raise argparse.ArgumentTypeError(
            "Wait condition must be SPEC_ID:SEED:GEN_ATTEMPTS:RENDER_ATTEMPTS"
        ) from error


def terminal(condition: tuple[str, int, int, int]) -> tuple[bool, str]:
    spec_id, seed, target_generate, target_render = condition
    manifest_path = RUN_ROOT / spec_id / f"seed_{seed}" / "run_manifest.json"
    if not manifest_path.exists():
        return False, "manifest_missing"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, "manifest_unreadable"
    generate = [a for a in manifest.get("attempts", []) if a.get("phase") == "generate"]
    render = [a for a in manifest.get("attempts", []) if a.get("phase") == "render"]
    if len(generate) < target_generate:
        return False, f"generate={len(generate)}/{target_generate}"
    if generate[-1].get("success") is not True:
        return True, f"generation_terminal_failure attempts={len(generate)}"
    if len(render) < target_render:
        return False, f"render={len(render)}/{target_render}"
    return True, f"render_terminal success={render[-1].get('success')}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-run", action="append", type=parse_wait, required=True)
    parser.add_argument("--task", action="append", required=True)
    parser.add_argument("--gpus", type=int, nargs="+", required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--max-wait-hours", type=float, default=13.0)
    parser.add_argument("--min-free-gib", type=float, default=50.0)
    args = parser.parse_args()
    if args.poll_seconds < 5 or args.poll_seconds > 60:
        parser.error("--poll-seconds must be between 5 and 60")
    if args.max_wait_hours <= 0:
        parser.error("--max-wait-hours must be positive")

    deadline = time.monotonic() + args.max_wait_hours * 3600
    while True:
        states = [terminal(condition) for condition in args.wait_run]
        summary = "; ".join(
            f"{condition[0]}/seed_{condition[1]}={state[1]}"
            for condition, state in zip(args.wait_run, states)
        )
        print(f"RECOVERY_WAIT {summary}", flush=True)
        if all(done for done, _ in states):
            break
        if time.monotonic() >= deadline:
            print("RECOVERY_ABORT wait_timeout", flush=True)
            return 124
        time.sleep(args.poll_seconds)

    command = [
        sys.executable,
        str(TASKLIST_RUNNER),
        "--phase",
        "all",
        "--workers",
        str(args.workers),
        "--gpus",
        *(str(gpu) for gpu in args.gpus),
        "--force",
        "--min-free-gib",
        str(args.min_free_gib),
    ]
    for task in args.task:
        command.extend(("--task", task))
    print(f"RECOVERY_LAUNCH tasks={len(args.task)}", flush=True)
    return subprocess.run(command, cwd=BASELINES.parent, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
