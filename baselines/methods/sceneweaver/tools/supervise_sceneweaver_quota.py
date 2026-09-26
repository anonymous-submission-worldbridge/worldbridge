#!/usr/bin/env python3
"""Resume the frozen SceneWeaver matrix across provider quota windows."""

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


# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_PYTHON = _wb_paths["WORLDBRIDGE_PYTHON"]


import argparse
import datetime as dt
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
REPO = BASELINES.parent
PLANNER_PYTHON = Path(f"{_wb_WORLDBRIDGE_PYTHON}")
RUNNER = BASELINES / "methods/sceneweaver/run_matrix_compat.py"
PRUNER = BASELINES / "methods/sceneweaver/tools/prune_sceneweaver_intermediates.py"
TERMINAL_MARKERS = (
    "SUCCESS",
    "PLANNER_BUDGET_EXHAUSTED",
    "RENDER_VALIDATION_FAILED",
)
PAUSE_RE = re.compile(r"SCENEWEAVER_RATE_LIMIT_PAUSE .*reset_epoch_ms=(\d+)")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def terminal_counts(data_root: Path) -> dict[str, int]:
    counts = {marker: 0 for marker in TERMINAL_MARKERS}
    counts["invalid_multiple_markers"] = 0
    method_root = data_root / "indoor/sceneweaver"
    for run_dir in method_root.glob("*/seed_*"):
        present = [
            marker for marker in TERMINAL_MARKERS if (run_dir / marker).is_file()
        ]
        if len(present) == 1:
            counts[present[0]] += 1
        elif len(present) > 1:
            counts["invalid_multiple_markers"] += 1
    counts["total"] = sum(counts[marker] for marker in TERMINAL_MARKERS)
    return counts


def wait_until(epoch_ms: int, state_path: Path, state: dict) -> None:
    while True:
        remaining = epoch_ms / 1000 - time.time()
        if remaining <= 0:
            return
        state.update(
            {
                "status": "waiting_for_provider_reset",
                "updated_at": utc_now(),
                "pause_until_epoch_ms": epoch_ms,
                "remaining_seconds": round(remaining, 1),
            }
        )
        atomic_json(state_path, state)
        print(
            f"SCENEWEAVER_SUPERVISOR_WAIT remaining_s={remaining:.1f} "
            f"reset_epoch_ms={epoch_ms}",
            flush=True,
        )
        time.sleep(min(60.0, remaining))


def run_pruner(data_root: Path, results_root: Path) -> None:
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    output = results_root / f"prune_supervisor_{stamp}.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(PRUNER),
            "--data-root",
            str(data_root),
            "--output",
            str(output),
            "--execute",
        ],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    print(completed.stdout.strip(), flush=True)
    if completed.returncode != 0:
        raise RuntimeError(f"pruner failed with exit code {completed.returncode}")


def matrix_command(args: argparse.Namespace) -> list[str]:
    return [
        str(PLANNER_PYTHON),
        str(RUNNER),
        "--workers",
        str(args.workers),
        "--gpus",
        *[str(gpu) for gpu in args.gpus],
        "--seeds",
        "0",
        "1",
        "2",
        "3",
        "--data-root",
        str(args.data_root),
        "--journal",
        str(args.journal),
        "--min-free-gib",
        str(args.min_free_gib),
        "--min-free-gpu-mib",
        str(args.min_free_gpu_mib),
        "--generation-timeout-s",
        "21600",
        "--render-timeout-s",
        "10800",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--gpus", type=int, nargs="+", default=[0, 2, 3])
    parser.add_argument("--min-free-gib", type=float, default=100.0)
    parser.add_argument("--min-free-gpu-mib", type=int, default=8000)
    parser.add_argument("--pause-until-epoch-ms", type=int, default=0)
    args = parser.parse_args()
    args.data_root = args.data_root.resolve()
    args.results_root = args.results_root.resolve()
    args.journal = args.journal.resolve()
    for path in (args.data_root, args.results_root, args.journal):
        try:
            path.relative_to(BASELINES.resolve())
        except ValueError as error:
            raise ValueError(
                f"all mutable paths must stay below {BASELINES}: {path}"
            ) from error

    state_path = args.results_root / "quota_supervisor_state.json"
    log_root = args.results_root / "supervisor_logs"
    log_root.mkdir(parents=True, exist_ok=True)
    state = {
        "started_at": utc_now(),
        "command": matrix_command(args),
        "status": "starting",
    }
    pause_until = args.pause_until_epoch_ms
    active: subprocess.Popen[str] | None = None

    def stop_child(signum, _frame):
        nonlocal active
        state.update({"status": "stopping", "signal": signum, "updated_at": utc_now()})
        atomic_json(state_path, state)
        if active is not None and active.poll() is None:
            os.killpg(active.pid, signal.SIGTERM)
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGINT, stop_child)
    signal.signal(signal.SIGTERM, stop_child)

    while True:
        counts = terminal_counts(args.data_root)
        state["terminal_counts"] = counts
        if counts["invalid_multiple_markers"]:
            raise RuntimeError("a run contains multiple terminal markers")
        if counts["total"] == 100:
            state.update({"status": "complete", "updated_at": utc_now()})
            atomic_json(state_path, state)
            print(
                f"SCENEWEAVER_SUPERVISOR_COMPLETE counts={json.dumps(counts)}",
                flush=True,
            )
            return 0

        if pause_until:
            wait_until(pause_until + 15_000, state_path, state)
            pause_until = 0

        stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
        log_path = log_root / f"matrix_{stamp}.log"
        state.update(
            {
                "status": "matrix_running",
                "updated_at": utc_now(),
                "matrix_log": str(log_path),
                "terminal_counts": counts,
            }
        )
        atomic_json(state_path, state)
        reset_epochs: list[int] = []
        with log_path.open("w", encoding="utf-8") as log_handle:
            active = subprocess.Popen(
                matrix_command(args),
                cwd=REPO,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                bufsize=1,
            )
            assert active.stdout is not None
            for line in active.stdout:
                print(line, end="", flush=True)
                log_handle.write(line)
                log_handle.flush()
                match = PAUSE_RE.search(line)
                if match:
                    reset_epochs.append(int(match.group(1)))
            exit_code = active.wait()
            active = None

        run_pruner(args.data_root, args.results_root)
        counts = terminal_counts(args.data_root)
        state.update(
            {
                "updated_at": utc_now(),
                "last_matrix_exit_code": exit_code,
                "terminal_counts": counts,
            }
        )
        if counts["total"] == 100:
            continue
        if reset_epochs:
            pause_until = max(reset_epochs)
            state.update(
                {
                    "status": "provider_rate_limited",
                    "pause_until_epoch_ms": pause_until,
                }
            )
            atomic_json(state_path, state)
            continue

        state.update({"status": "stopped_nonquota_failure"})
        atomic_json(state_path, state)
        print(
            f"SCENEWEAVER_SUPERVISOR_STOP_NONQUOTA exit_code={exit_code} "
            f"counts={json.dumps(counts)}",
            flush=True,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
