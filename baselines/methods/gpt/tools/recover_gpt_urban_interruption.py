#!/usr/bin/env python3
"""Exactly three explicitly authorized fifth attempts, concurrently on GPUs."""

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

from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
import os
from pathlib import Path
import sys
import time

BASE = _BASELINE_PROJECT_ROOT / "baselines"
sys.path[:0] = [str(BASE / "tools"), str((BASE / "methods")), str(BASE)]
import baselines.methods.gpt.tools.finish_gpt_urban as runner

REVISION = (
    BASE
    / "methods/gpt/protocol/generation/gpt6_astra_interruption_recovery_20260909.json"
)
OUTPUT = BASE / "results/gpt6_astra/urban_interruption_recovery_20260909"


def main():
    runner.verify_lock()
    revision = json.loads(REVISION.read_text())
    runs = [BASE / "data/table2/urban/gpt6_astra" / p for p in revision["targets"]]
    if revision["max_attempts_for_exact_targets"] != 5 or len(runs) != 3:
        raise RuntimeError("Unexpected authorization scope")
    for run in runs:
        m = json.loads((run / "run_manifest.json").read_text())
        a = m.get("render_attempts", [])
        if (
            runner.eligibility(m, 5) != "ready"
            or len(a) != 4
            or not a[-1].get("infrastructure_interruption")
        ):
            raise RuntimeError(
                "Target is not an interrupted fourth attempt: " + str(run)
            )
    # The old r1 exhausted set excludes these exact targets. Independently
    # verify no worker still owns them before creating any attempt record.
    for path in Path("/proc").iterdir():
        if path.name.isdigit():
            process = runner.proc(int(path.name))
            if process and any(str(run) in process["command"] for run in runs):
                raise RuntimeError("A target still has a live worker")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    guard = (OUTPUT / "controller.lock").open("a")
    fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (OUTPUT / "state.json").exists():
        raise RuntimeError("Existing recovery; refuse duplicate")
    state = dict(
        started_at_utc=runner.adapter.utc(),
        status="running",
        completed=[],
        errors=[],
        amendment=str(REVISION.relative_to(BASE)),
        amendment_sha256=runner.adapter.digest(REVISION),
        controller_sha256=runner.adapter.digest(__file__),
        max_attempts=5,
        active=[],
    )
    runner.adapter.write_json(OUTPUT / "state.json", state)
    pid = os.fork()
    if pid:
        print("DETACHED_INTERRUPTION_RECOVERY", pid, flush=True)
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
    runner.OUTPUT, runner.REVISION = OUTPUT, REVISION
    state["controller_pid"] = os.getpid()
    pending = list(runs)
    jobs = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        while pending or jobs:
            for future in list(jobs):
                if future.done():
                    run, gpu = jobs.pop(future)
                    try:
                        result = future.result()
                        state["completed"].append(
                            dict(
                                run=str(run.relative_to(BASE)),
                                gpu=gpu,
                                render_success=bool(result.get("render_success")),
                                failure_class=result.get("failure_class"),
                            )
                        )
                        if (
                            not result.get("render_success")
                            and result.get("failure_class") != "quality"
                        ):
                            state["errors"].append(
                                "Infrastructure remains: " + str(run)
                            )
                    except Exception as error:
                        state["errors"].append(str(error))
            free = runner.gpu_free()
            used = {gpu for run, gpu in jobs.values()}
            # Prefer 1/2/3, leaving GPU 0 for IQA, but allow shared devices
            # with enough remaining VRAM; never require utilization zero.
            candidates = sorted(
                [g for g in free if g not in used and free[g] >= 24576],
                key=lambda g: (g == 0, -free[g]),
            )
            for gpu in candidates:
                if not pending:
                    break
                run = pending.pop(0)
                jobs[pool.submit(runner.render_once, run, gpu, 5)] = run, gpu
            state.update(
                updated_at_utc=runner.adapter.utc(),
                gpu_free_mib=free,
                active=[
                    dict(run=str(run.relative_to(BASE)), gpu=gpu)
                    for run, gpu in jobs.values()
                ],
            )
            runner.adapter.write_json(OUTPUT / "state.json", state)
            if pending or jobs:
                time.sleep(20)
    state.update(
        status="complete" if not state["errors"] else "needs_triage",
        ended_at_utc=runner.adapter.utc(),
    )
    runner.adapter.write_json(OUTPUT / "state.json", state)


if __name__ == "__main__":
    main()
