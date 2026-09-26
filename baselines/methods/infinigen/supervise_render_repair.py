#!/usr/bin/env python3
"""Repair GPU-infrastructure renders as each generation recovery finishes."""

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
sys.path.insert(0, str(BASELINES / "tools"))

from baselines.methods.infinigen.tools.audit_infinigen_matrix import ADAPTER_SHA256
from baselines.methods.infinigen.tools.audit_infinigen_matrix import DATA_ROOT
from baselines.methods.infinigen.tools.audit_infinigen_matrix import PROTOCOL_SHA256
from baselines.methods.infinigen.tools.audit_infinigen_matrix import classify
from baselines.methods.infinigen.tools.audit_infinigen_matrix import load_specs
from baselines.methods.infinigen.supervise_recovery import parse_wait
from baselines.methods.infinigen.supervise_recovery import terminal  # noqa: E402


def has_formal_generation(run_dir: Path) -> bool:
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.exists() or not (run_dir / "scene/scene.blend").exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return any(
        attempt.get("phase") == "generate"
        and attempt.get("protocol_sha256") == PROTOCOL_SHA256
        and attempt.get("adapter_sha256") == ADAPTER_SHA256
        and attempt.get("success") is True
        for attempt in manifest.get("attempts", [])
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-run", action="append", type=parse_wait, required=True)
    parser.add_argument("--gpus", type=int, nargs="+", required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--max-wait-hours", type=float, default=72.0)
    parser.add_argument("--min-free-gib", type=float, default=50.0)
    args = parser.parse_args()
    if args.poll_seconds < 5 or args.poll_seconds > 60:
        parser.error("--poll-seconds must be between 5 and 60")

    deadline = time.monotonic() + args.max_wait_hours * 3600
    attempted: set[str] = set()
    repair_failures = 0
    while True:
        states = [terminal(condition) for condition in args.wait_run]
        summary = "; ".join(
            f"{condition[0]}/seed_{condition[1]}={state[1]}"
            for condition, state in zip(args.wait_run, states)
        )
        print(f"RENDER_REPAIR_WAIT {summary}", flush=True)

        tasks = []
        for spec_id in load_specs():
            for seed in range(4):
                task = f"{spec_id}:{seed}"
                run_dir = DATA_ROOT / spec_id / f"seed_{seed}"
                if (
                    task not in attempted
                    and classify(run_dir) == "infrastructure_candidate"
                    and has_formal_generation(run_dir)
                ):
                    tasks.append(task)
        if tasks:
            attempted.update(tasks)
            for task in tasks:
                print(f"RENDER_REPAIR_SELECT {task}", flush=True)
            command = [
                sys.executable,
                str((BASELINES / "methods/infinigen/run_tasklist.py")),
                "--phase",
                "render",
                "--workers",
                str(args.workers),
                "--gpus",
                *(str(gpu) for gpu in args.gpus),
                "--min-free-gib",
                str(args.min_free_gib),
            ]
            for task in tasks:
                command.extend(("--task", task))
            print(f"RENDER_REPAIR_LAUNCH tasks={len(tasks)}", flush=True)
            returncode = subprocess.run(
                command, cwd=BASELINES.parent, check=False
            ).returncode
            if returncode:
                repair_failures += 1
                print(
                    f"RENDER_REPAIR_BATCH_FAILED returncode={returncode}",
                    flush=True,
                )
            continue

        if all(done for done, _ in states):
            print(
                "RENDER_REPAIR_COMPLETE "
                f"attempted={len(attempted)} failed_batches={repair_failures}",
                flush=True,
            )
            return int(repair_failures > 0)
        if time.monotonic() >= deadline:
            print("RENDER_REPAIR_ABORT wait_timeout", flush=True)
            return 124
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
