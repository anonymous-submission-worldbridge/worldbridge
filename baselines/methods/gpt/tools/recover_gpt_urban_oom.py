#!/usr/bin/env python3
"""Evidence-based triage of three OOM renders, within their original caps."""

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
import fcntl
import json
import os
from pathlib import Path
import shutil
import sys
import time

BASE = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(BASE / "tools"))
import baselines.methods.gpt.tools.finish_gpt_urban as runner

TARGETS = (
    ("urban_park_edge_four_way_15", 0),
    ("urban_park_edge_four_way_15", 2),
    ("urban_park_edge_t_junction_16", 0),
)
OUTPUT = BASE / "results/gpt6_astra/urban_oom_recovery_20260909"


def main():
    global TARGETS, OUTPUT
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--second-wave", action="store_true")
    group.add_argument("--controller-interruption", action="store_true")
    args = parser.parse_args()
    if args.controller_interruption:
        from baselines.methods.gpt.tools.recover_gpt_urban_interruption import (
            main as recover_interruption,
        )

        recover_interruption()
        return
    if args.second_wave:
        TARGETS = (
            ("urban_park_edge_main_side_17", 3),
            ("urban_leisure_civic_four_way_20", 0),
        )
        OUTPUT = BASE / "results/gpt6_astra/urban_oom_recovery_20260909_wave2"
    runner.verify_lock()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    guard = (OUTPUT / "controller.lock").open("a")
    fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (OUTPUT / "state.json").exists():
        raise RuntimeError("Existing recovery; no implicit restart")
    state = dict(
        started_at_utc=runner.adapter.utc(),
        status="running",
        max_attempts=3,
        rationale="Frozen classifier matches 'out of memory' but not 'out of GPU memory'. Logs prove resource OOM, not a scene defect or missing CUDA setup.",
        completed=[],
        errors=[],
        controller_sha256=runner.adapter.digest(__file__),
    )
    runner.adapter.write_json(OUTPUT / "state.json", state)
    pid = os.fork()
    if pid:
        print("DETACHED_OOM_RECOVERY", pid, flush=True)
        return
    os.setsid()
    fd = os.open(
        OUTPUT / "controller.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o664
    )
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    os.close(fd)
    null = os.open("/dev/null", os.O_RDONLY)
    os.dup2(null, 0)
    os.close(null)
    runner.OUTPUT = OUTPUT
    for sid, seed in TARGETS:
        run = BASE / "data/table2/urban/gpt6_astra" / sid / f"seed_{seed}"
        path = run / "run_manifest.json"
        m = json.loads(path.read_text())
        if m.get("render_success") or m.get("failure_class") == "quality":
            continue
        attempts = m["render_attempts"]
        if not attempts[-1].get("ended_at_utc") or len(attempts) >= 3:
            raise RuntimeError("No original retry available")
        logs = run / f"logs/render_{attempts[-1]['index']:02d}"
        stderr = (logs / "stderr.log").read_text()
        if "System is out of GPU memory" not in stderr:
            raise RuntimeError("OOM evidence missing")
        backup = OUTPUT / "triage_previous" / sid / f"seed_{seed}"
        backup.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup / "run_manifest.json")
        m.pop("acceleration_setup_error", None)
        m["oom_triage"] = dict(
            at_utc=runner.adapter.utc(),
            original_error="acceleration_setup_error",
            diagnosis="Explicit GPU OOM during OptiX build/denoiser allocation",
            stderr_sha256=runner.adapter.digest(logs / "stderr.log"),
            retry_policy="Original maximum three attempts; no increase",
            min_free_mib=24576,
        )
        runner.adapter.write_json(path, m)
        while True:
            free = runner.gpu_free()
            eligible = [g for g in free if free[g] >= 24576]
            state.update(
                updated_at_utc=runner.adapter.utc(),
                current=f"{sid}/seed_{seed}",
                gpu_free_mib=free,
            )
            runner.adapter.write_json(OUTPUT / "state.json", state)
            if eligible:
                gpu = max(eligible, key=free.get)
                break
            time.sleep(20)
        result = runner.render_once(run, gpu, 3)
        state["completed"].append(
            dict(
                spec_id=sid,
                seed=seed,
                gpu=gpu,
                render_success=bool(result.get("render_success")),
                failure_class=result.get("failure_class"),
            )
        )
        if (
            not result.get("render_success")
            and result.get("failure_class") != "quality"
        ):
            state["errors"].append(f"Recovery still infrastructure: {sid}/seed_{seed}")
        runner.adapter.write_json(OUTPUT / "state.json", state)
    state.update(
        status="complete" if not state["errors"] else "needs_triage",
        ended_at_utc=runner.adapter.utc(),
    )
    runner.adapter.write_json(OUTPUT / "state.json", state)


if __name__ == "__main__":
    main()
