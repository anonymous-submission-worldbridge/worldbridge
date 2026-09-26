"""One bounded earliest-deadline GPU time slice; never alter attempt budgets."""

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
from worldbridge.paths import (
    expand_paths as _wb_expand_paths,
    path_variables as _wb_path_variables,
)

_wb_paths = _wb_path_variables()

import json
import os
from pathlib import Path
import signal
import sys
import time
from datetime import datetime

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path[:0] = [str(ROOT / "tools"), str((ROOT / "methods"))]
from baselines.methods.gpt.tools.accelerate_gpt import proc
from baselines.methods.gpt.tools.accelerate_gpt import verify_lock
from baselines.methods.gpt.adapter import utc
from baselines.methods.gpt.adapter import write_json


def rendering(run):
    m = json.loads((run / "run_manifest.json").read_text())
    attempt = m["render_attempts"][-1]
    if attempt.get("ended_at_utc") or attempt["gpu"] != 3 or m.get("render_success"):
        raise RuntimeError("The exact target is no longer rendering on GPU 3")
    matches = []
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            p = proc(int(path.name))
        except (FileNotFoundError, PermissionError):
            continue
        if (
            p
            and p["uid"] == os.getuid()
            and p["command"][0:1] == [_wb_expand_paths("${BLENDER_BIN}")]
        ):
            c = p["command"]
            if (
                "--run-dir" in c
                and Path(c[c.index("--run-dir") + 1]).resolve() == run
                and c[-2:] == ["--phase", "render"]
            ):
                matches.append(p)
    if len(matches) != 1:
        raise RuntimeError("No unique owned Blender process for exact run")
    deadline = (
        datetime.fromisoformat(attempt["started_at_utc"]).timestamp()
        + attempt["timeout_limit_s"]
    )
    return matches[0], attempt, deadline


def main():
    verify_lock()
    delayed = (
        ROOT / "data/table2/urban/gpt6_astra/urban_residential_main_side_02/seed_3"
    )
    priority = ROOT / "data/table2/urban/gpt6_astra/urban_commercial_four_way_05/seed_3"
    child, attempt, deadline = rendering(delayed)
    first, first_attempt, first_deadline = rendering(priority)
    seconds = min(180, first_deadline - time.time() - 15)
    if (
        first_deadline >= deadline
        or seconds < 30
        or deadline - time.time() < seconds + 300
    ):
        raise RuntimeError(
            "No safe bounded earliest-deadline time-slice window remains"
        )
    record_path = ROOT / "results/gpt6_astra/acceleration_20260909/gpu3_time_slice.json"
    if record_path.exists():
        raise RuntimeError(
            "This bounded intervention was already recorded; do not repeat"
        )
    record = {
        "started_at_utc": utc(),
        "delayed_pid": child["pid"],
        "priority_pid": first["pid"],
        "delayed_run": str(delayed),
        "priority_run": str(priority),
        "maximum_pause_s": seconds,
        "original_deadlines_unchanged": True,
        "status": "prepared",
    }
    write_json(record_path, record)
    paused = False

    def restore():
        nonlocal paused
        current = proc(child["pid"])
        if (
            paused
            and current
            and current["birth"] == child["birth"]
            and current["uid"] == os.getuid()
        ):
            os.kill(child["pid"], signal.SIGCONT)
        paused = False

    def interrupted(signum, frame):
        restore()
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        paused = True
        os.kill(child["pid"], signal.SIGSTOP)
        started = time.monotonic()
        record.update(status="temporarily_yielding", stopped_at_utc=utc())
        write_json(record_path, record)
        print(
            "OWN_RENDER_TEMPORARILY_YIELDS",
            child["pid"],
            "maximum_seconds",
            seconds,
            flush=True,
        )
        while time.monotonic() - started < seconds:
            p = proc(first["pid"])
            if not p or p["birth"] != first["birth"] or p["state"] == "Z":
                break
            time.sleep(2)
    finally:
        restore()
        record.update(status="resumed", resumed_at_utc=utc())
        write_json(record_path, record)
        print("OWN_RENDER_RESUMED", child["pid"], flush=True)


if __name__ == "__main__":
    main()
