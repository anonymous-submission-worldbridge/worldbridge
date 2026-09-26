#!/usr/bin/env python3
"""One extra Urban render lane on GPU 0; unchanged renderer and retry caps.

Wait for the three OOM recoveries first. Take the queue from its opposite end,
using the same per-run exclusive lock and eligibility recheck as the main lane.
"""

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

import fcntl
import json
import os
from pathlib import Path
import sys
import time

BASE = _BASELINE_PROJECT_ROOT / "baselines"
sys.path[:0] = [str(BASE / "tools"), str((BASE / "methods")), str(BASE)]
import baselines.methods.gpt.tools.finish_gpt_urban as finish
import baselines.methods.gpt.adapter as adapter
from baselines.methods.gpt.tools.accelerate_gpt import gpu_free
from baselines.methods.gpt.tools.accelerate_gpt import verify_lock

OUTPUT = BASE / "results/gpt6_astra/urban_extra_gpu0_20260909"
MAIN = BASE / "results/gpt6_astra/urban_finish_20260909_r1/state.json"
OOM = BASE / "results/gpt6_astra/urban_oom_recovery_20260909/state.json"


def main():
    verify_lock()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    guard = (OUTPUT / "controller.lock").open("a")
    fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (OUTPUT / "state.json").exists():
        raise RuntimeError("Existing supplemental controller; refusing duplicate")
    state = dict(
        started_at_utc=adapter.utc(),
        status="waiting_oom_recovery",
        completed=[],
        errors=[],
        controller_sha256=adapter.digest(__file__),
        gpu=0,
        minimum_free_mib=24576,
        concurrency=1,
        policy="Additional resource lane only; original scene, renderer and attempt caps unchanged",
    )
    adapter.write_json(OUTPUT / "state.json", state)
    pid = os.fork()
    if pid:
        print("DETACHED_EXTRA_GPU0", pid, flush=True)
        return
    os.setsid()
    fd = os.open(
        OUTPUT / "controller.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o664
    )
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    os.close(fd)
    fd = os.open("/dev/null", os.O_RDONLY)
    os.dup2(fd, 0)
    os.close(fd)
    state["controller_pid"] = os.getpid()
    finish.OUTPUT = OUTPUT
    seen = set()
    while True:
        state["updated_at_utc"] = adapter.utc()
        recovery = json.loads(OOM.read_text())
        if recovery.get("status") == "running":
            adapter.write_json(OUTPUT / "state.json", state)
            time.sleep(20)
            continue
        main_state = json.loads(MAIN.read_text())
        candidates = []
        for relative, cap in reversed(list(main_state["max_attempts"].items())):
            if relative in seen or relative in main_state["active_runs"]:
                continue
            run = BASE / relative
            manifest = json.loads((run / "run_manifest.json").read_text())
            if finish.eligibility(manifest, cap) == "ready" and not manifest.get(
                "acceleration_setup_error"
            ):
                candidates.append((relative, run, cap))
        if not candidates:
            state["status"] = "queue_drained"
            adapter.write_json(OUTPUT / "state.json", state)
            break
        free = gpu_free()
        state.update(status="waiting_gpu_memory", gpu_free_mib=free)
        adapter.write_json(OUTPUT / "state.json", state)
        if free.get(0, 0) < 24576:
            time.sleep(20)
            continue
        relative, run, cap = candidates[0]
        seen.add(relative)
        state.update(status="rendering", current=relative)
        adapter.write_json(OUTPUT / "state.json", state)
        try:
            result = finish.render_once(run, 0, cap)
            state["completed"].append(
                dict(
                    run=relative,
                    render_success=result.get("render_success"),
                    failure_class=result.get("failure_class"),
                )
            )
        except (BlockingIOError, RuntimeError) as error:
            state["errors"].append(dict(run=relative, error=str(error)))
        state.pop("current", None)
        adapter.write_json(OUTPUT / "state.json", state)
        time.sleep(2)


if __name__ == "__main__":
    main()
