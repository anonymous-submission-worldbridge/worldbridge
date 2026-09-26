#!/usr/bin/env python3
"""Cut over the broad matrix runner to an explicit tail at a safe boundary."""

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
import signal
import subprocess
import sys
import time
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(BASELINES / "tools"))

from baselines.methods.infinigen.tools.audit_infinigen_matrix import DATA_ROOT
from baselines.methods.infinigen.tools.audit_infinigen_matrix import (
    classify,
)  # noqa: E402
from baselines.methods.infinigen.supervise_recovery import parse_wait
from baselines.methods.infinigen.supervise_recovery import terminal  # noqa: E402


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def validate_runner(pid: int) -> None:
    cmdline_path = Path(f"/proc/{pid}/cmdline")
    if not cmdline_path.exists():
        raise RuntimeError(f"Runner PID {pid} no longer exists")
    cmdline = cmdline_path.read_bytes().replace(b"\0", b" ").decode(errors="replace")
    required = "baselines/methods/infinigen/run.py --phase all --workers 2 --gpus 2 5"
    if required not in cmdline:
        raise RuntimeError(f"PID {pid} is not the expected matrix runner: {cmdline}")
    if os.getpgid(pid) != pid:
        raise RuntimeError(f"PID {pid} is not an independent process-group leader")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner-pid", type=int, required=True)
    parser.add_argument("--wait-run", action="append", type=parse_wait, required=True)
    parser.add_argument("--candidate", action="append", required=True)
    parser.add_argument("--gpus", type=int, nargs="+", required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--poll-seconds", type=int, default=5)
    parser.add_argument("--max-wait-hours", type=float, default=13.0)
    parser.add_argument("--min-free-gib", type=float, default=50.0)
    args = parser.parse_args()
    if args.poll_seconds < 2 or args.poll_seconds > 60:
        parser.error("--poll-seconds must be between 2 and 60")
    validate_runner(args.runner_pid)

    deadline = time.monotonic() + args.max_wait_hours * 3600
    while True:
        states = [terminal(condition) for condition in args.wait_run]
        summary = "; ".join(
            f"{condition[0]}/seed_{condition[1]}={state[1]}"
            for condition, state in zip(args.wait_run, states)
        )
        print(f"MAIN_CUTOFF_WAIT {summary}", flush=True)
        if all(done for done, _ in states):
            break
        if not process_exists(args.runner_pid):
            print("MAIN_CUTOFF_ABORT runner_exited_early", flush=True)
            return 125
        if time.monotonic() >= deadline:
            print("MAIN_CUTOFF_ABORT wait_timeout", flush=True)
            return 124
        time.sleep(args.poll_seconds)

    validate_runner(args.runner_pid)
    print(f"MAIN_CUTOFF_SIGNAL pgid={args.runner_pid} signal=SIGINT", flush=True)
    os.killpg(args.runner_pid, signal.SIGINT)
    # ThreadPoolExecutor handles the first KeyboardInterrupt by entering
    # shutdown(wait=True).  A second SIGINT is needed to interrupt that join;
    # keep both signals strictly scoped to the already validated process group.
    first_stop_deadline = time.monotonic() + 10
    while process_exists(args.runner_pid) and time.monotonic() < first_stop_deadline:
        time.sleep(1)
    if process_exists(args.runner_pid):
        validate_runner(args.runner_pid)
        print(
            f"MAIN_CUTOFF_SIGNAL pgid={args.runner_pid} signal=SIGINT second=true",
            flush=True,
        )
        os.killpg(args.runner_pid, signal.SIGINT)
    stop_deadline = time.monotonic() + 50
    while process_exists(args.runner_pid) and time.monotonic() < stop_deadline:
        time.sleep(1)
    if process_exists(args.runner_pid):
        print("MAIN_CUTOFF_ABORT runner_did_not_exit_after_sigint", flush=True)
        return 126

    pending = []
    for candidate in args.candidate:
        spec_id, seed_text = candidate.rsplit(":", 1)
        seed = int(seed_text)
        status = classify(DATA_ROOT / spec_id / f"seed_{seed}")
        print(f"MAIN_CUTOFF_AUDIT {spec_id}/seed_{seed}={status}", flush=True)
        if status not in ("formal_success", "quality_failure"):
            pending.append(candidate)
    if not pending:
        print("MAIN_CUTOFF_COMPLETE no_pending_tail_tasks", flush=True)
        return 0

    command = [
        sys.executable,
        str((BASELINES / "methods/infinigen/run_tasklist.py")),
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
    for task in pending:
        command.extend(("--task", task))
    print(f"MAIN_CUTOFF_LAUNCH tasks={len(pending)}", flush=True)
    return subprocess.run(command, cwd=BASELINES.parent, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
