#!/usr/bin/env python3
"""Finish only Astra Urban with a disclosed, user-authorized render budget.

Original renderer, generated code, acceptance rules and 28 frozen sources are
unchanged. Old draining workers retain their original deadlines and ownership.
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

from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

BASE = _BASELINE_PROJECT_ROOT / "baselines"
sys.path[:0] = [str(BASE), str((BASE / "methods")), str(BASE / "tools")]
import baselines.methods.gpt.adapter as adapter
import baselines.methods.gpt.run as matrix
from baselines.methods.gpt.tools.accelerate_gpt import proc
from baselines.methods.gpt.tools.accelerate_gpt import children
from baselines.methods.gpt.tools.accelerate_gpt import verify_lock
from baselines.methods.gpt.tools.accelerate_gpt import gpu_free
from baselines.methods.gpt.tools.accelerate_gpt import finish_blender

OLD_PID = 3147646
OLD_STATE = BASE / "results/gpt6_astra/resume_20260909_0443/state.json"
OUTPUT = BASE / "results/gpt6_astra/urban_finish_20260909"
REVISION = (
    BASE / "methods/gpt/protocol/generation/gpt6_astra_render_amendment_20260909.json"
)


def eligibility(m, max_attempts):
    if m.get("render_success") or m.get("failure_class") == "quality":
        return "terminal"
    if any(
        a and not a[-1].get("ended_at_utc")
        for a in (
            m.get("attempts", []),
            m.get("build_attempts", []),
            m.get("render_attempts", []),
        )
    ):
        return "old_worker"
    if not m.get("build_success"):
        return "build_pending"
    if len(m.get("render_attempts", [])) >= max_attempts:
        return "exhausted"
    return "ready"


def render_once(run, gpu, max_attempts):
    verify_lock()
    if shutil.disk_usage(BASE).free < 50 * 1024**3:
        raise RuntimeError("Storage guard: less than 50 GiB free")
    guard = (run / "urban_recovery.lock").open("a")
    fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        path = run / "run_manifest.json"
        m = json.loads(path.read_text())
        if eligibility(m, max_attempts) != "ready":
            raise RuntimeError("Run changed at scheduling boundary: " + str(run))
        if adapter.digest(run / "scene/generated.py") != m["generated_code_sha256"]:
            raise RuntimeError("Generated code changed")
        config = json.loads(
            ((BASE / "methods/gpt/protocol/generation/gpt6_astra.json")).read_text()
        )
        renderer = BASE / "methods/gpt/tools/blender_render_gpt.py"
        if m["renderer_sha256"] != adapter.digest(renderer):
            raise RuntimeError("Renderer changed")
        backup = OUTPUT / "previous" / run.parent.name / run.name
        backup.mkdir(parents=True, exist_ok=True)
        if not (backup / "run_manifest.json").exists():
            shutil.copy2(path, backup / "run_manifest.json")
        admitted = matrix.wait_gpu(gpu, 8192)
        index = len(m.get("render_attempts", [])) + 1
        logs = run / f"logs/render_{index:02d}"
        logs.mkdir(parents=True, exist_ok=False)
        command = [
            "bwrap",
            "--die-with-parent",
            "--unshare-net",
            "--ro-bind",
            "/",
            "/",
            "--dev-bind",
            "/dev",
            "/dev",
            "--proc",
            "/proc",
            "--bind",
            str(run),
            str(run),
            "--tmpfs",
            "/tmp",
            "--tmpfs",
            "/home",
            "--chdir",
            str(run),
            config["blender_executable"],
            "-b",
            "--factory-startup",
            "-t",
            str(config.get("render_threads", 8)),
            "--python-exit-code",
            "11",
            str(run / "scene/scene.blend"),
            "--python",
            str(renderer),
            "--",
            "--run-dir",
            str(run),
            "--phase",
            "render",
        ]
        attempt = dict(
            index=index,
            started_at_utc=adapter.utc(),
            gpu=gpu,
            command=command,
            timeout_limit_s=7200,
            previous_protocol_timeout_s=1800,
            gpu_admitted_free_mib=admitted,
            gpu_policy="remaining_memory_sharing",
            resource_amendment=str(REVISION.relative_to(BASE)),
            original_attempts_preserved=True,
        )
        m.setdefault("render_attempts", []).append(attempt)
        m["render_budget_revision"] = dict(
            amendment=str(REVISION.relative_to(BASE)),
            timeout_limit_s=7200,
            max_attempts=max_attempts,
            changes="resources_only",
        )
        if index > 3:
            m["authorized_extra_render_attempt"] = dict(
                index=index, amendment=str(REVISION.relative_to(BASE))
            )
        adapter.write_json(path, m)
        env = dict(
            os.environ,
            CUDA_VISIBLE_DEVICES=str(gpu),
            TMPDIR=str(run / "tmp"),
            PYTHONDONTWRITEBYTECODE="1",
        )
        print(
            "RENDER_START",
            run.parent.name,
            run.name,
            "gpu",
            gpu,
            "attempt",
            index,
            flush=True,
        )
        rc, timeout = adapter.run_process(
            command, run, logs / "stdout.log", logs / "stderr.log", 7200, env=env
        )
        attempt.update(exit_code=rc, timeout=timeout, ended_at_utc=adapter.utc())
        m = finish_blender(run, m, "render", attempt, rc, timeout)
        adapter.write_json(path, m)
        print(
            "RENDER_END",
            run.parent.name,
            run.name,
            "success",
            m.get("render_success"),
            "failure",
            m.get("failure_class"),
            flush=True,
        )
        return m
    finally:
        guard.close()


def main():
    global OUTPUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--render-slots", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--resume-id")
    parser.add_argument("--detach", action="store_true")
    args = parser.parse_args()
    prior_output = OUTPUT
    if args.resume_id:
        if not args.resume_id.isalnum():
            raise ValueError("Alphanumeric resume ID required")
        OUTPUT = (
            BASE / "results/gpt6_astra" / ("urban_finish_20260909_" + args.resume_id)
        )
    lock = verify_lock()
    runs = []
    for line in (
        ((BASE / "protocol/generation/urban_specs.jsonl")).read_text().splitlines()
    ):
        spec = json.loads(line)
        runs += [
            BASE / "data/table2/urban/gpt6_astra" / spec["spec_id"] / f"seed_{s}"
            for s in range(4)
        ]
    manifests = {r: json.loads((r / "run_manifest.json").read_text()) for r in runs}
    prior = (
        json.loads((prior_output / "state.json").read_text())
        if args.resume_id
        else None
    )
    if prior:
        active_names = set(prior["active_runs"])
        for path in Path("/proc").iterdir():
            if not path.name.isdigit():
                continue
            try:
                row = proc(int(path.name))
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                continue
            if not row or row["uid"] != os.getuid() or row["pid"] == os.getpid():
                continue
            cmd = row["command"]
            if any(x.endswith("finish_gpt_urban.py") for x in cmd):
                raise RuntimeError("Another finish controller is live")
            if "--run-dir" in cmd:
                candidate = Path(cmd[cmd.index("--run-dir") + 1]).resolve()
                if str(candidate.relative_to(BASE)) in active_names:
                    raise RuntimeError("Interrupted run still has a live worker")
    old = proc(OLD_PID)
    protected = set()
    if old:
        if old["uid"] != os.getuid() or not any(
            x.endswith("accelerate_gpt.py") for x in old["command"]
        ):
            raise RuntimeError("Old PID identity mismatch")
        state = json.loads(OLD_STATE.read_text())
        if (
            state["status"] not in ("draining_after_error", "paused_error")
            or not state["errors"]
        ):
            raise RuntimeError("Old controller might dispatch work; refusing overlap")
        for row in children(OLD_PID):
            if "--run-dir" in row["command"]:
                protected.add(
                    Path(
                        row["command"][row["command"].index("--run-dir") + 1]
                    ).resolve()
                )
    # All runs already at the original cap or owned by the draining dispatcher
    # are eligible for exactly one additional attempt, never unlimited retries.
    caps = {
        r: 4
        if len(m["render_attempts"] if "render_attempts" in m else []) >= 3
        or r in protected
        else 3
        for r, m in manifests.items()
    }
    if prior:
        caps = {r: prior["max_attempts"][str(r.relative_to(BASE))] for r in runs}
    if args.check_only:
        print(
            json.dumps(
                dict(
                    runs=len(runs),
                    frozen_sources=len(lock["files_sha256"]),
                    protected=[str(r) for r in protected],
                    gpu_free_mib=gpu_free(),
                    counts=dict(
                        Counter(eligibility(m, caps[r]) for r, m in manifests.items())
                    ),
                )
            )
        )
        return
    OUTPUT.mkdir(parents=True, exist_ok=True)
    controller_guard = (OUTPUT / "controller.lock").open("a")
    fcntl.flock(controller_guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (OUTPUT / "state.json").exists():
        raise RuntimeError("Existing execution record; no implicit restart")
    if args.detach:
        pid = os.fork()
        if pid:
            print("DETACHED_CONTROLLER", pid, "output", str(OUTPUT), flush=True)
            return
        os.setsid()
        logfd = os.open(
            OUTPUT / "controller.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o664
        )
        nullfd = os.open("/dev/null", os.O_RDONLY)
        os.dup2(logfd, 1)
        os.dup2(logfd, 2)
        os.dup2(nullfd, 0)
        os.close(logfd)
        os.close(nullfd)
    interrupted = []
    if prior:
        for run, m in manifests.items():
            if str(run.relative_to(BASE)) not in prior["active_runs"]:
                continue
            attempts = m.get("render_attempts", [])
            if not attempts or attempts[-1].get("ended_at_utc"):
                continue
            archive = OUTPUT / "interrupted_previous" / run.parent.name / run.name
            archive.mkdir(parents=True, exist_ok=True)
            shutil.copy2(run / "run_manifest.json", archive / "run_manifest.json")
            attempts[-1].update(
                ended_at_utc=adapter.utc(),
                exit_code=None,
                timeout=False,
                infrastructure_interruption="Controller and worker disappeared; true exit status unavailable. Not a quality failure.",
                interruption_reconciled_by=str(OUTPUT.relative_to(BASE)),
            )
            m.update(
                failure_class="infrastructure",
                failure_reason="Render interrupted by unexpected controller exit",
            )
            adapter.write_json(run / "run_manifest.json", m)
            interrupted.append(str(run.relative_to(BASE)))
    state = dict(
        started_at_utc=adapter.utc(),
        status="running",
        controller_sha256=adapter.digest(__file__),
        controller_pid=os.getpid(),
        controller_birth=proc(os.getpid())["birth"],
        resumed_from=str(prior_output.relative_to(BASE)) if prior else None,
        reconciled_interruptions=interrupted,
        original_sources_sha256=lock["files_sha256"],
        render_slots_per_gpu=args.render_slots,
        amendment=str(REVISION.relative_to(BASE)),
        protected_old_runs=[str(r) for r in protected],
        max_attempts={str(r.relative_to(BASE)): caps[r] for r in runs},
        errors=[],
    )
    adapter.write_json(OUTPUT / "state.json", state)
    active, exhausted = {}, set()
    with ThreadPoolExecutor(max_workers=12) as pool:
        while True:
            manifests = {
                r: json.loads((r / "run_manifest.json").read_text()) for r in runs
            }
            for future in list(active):
                if not future.done():
                    continue
                run, gpu = active.pop(future)
                try:
                    manifests[run] = future.result()
                    if manifests[run].get("acceleration_setup_error"):
                        raise RuntimeError("Renderer setup failed: " + str(run))
                except Exception as error:
                    state["errors"].append(str(error))
                    exhausted.add(run)
            current_old = proc(OLD_PID)
            if old and (
                not current_old
                or current_old["birth"] != old["birth"]
                or current_old["state"] == "Z"
            ):
                protected.clear()
            busy = {r for r, gpu in active.values()}
            load = Counter(gpu for r, gpu in active.values())
            free = gpu_free()
            for run, m in manifests.items():
                if run in busy or run in protected or run in exhausted:
                    continue
                phase = eligibility(m, caps[run])
                if phase == "exhausted":
                    exhausted.add(run)
                    state["errors"].append(
                        "Authorized render cap exhausted: " + str(run)
                    )
                    continue
                if phase != "ready":
                    continue
                candidates = [
                    g for g in free if free[g] >= 8192 and load[g] < args.render_slots
                ]
                if not candidates:
                    break
                gpu = max(candidates, key=lambda g: (free[g] / (load[g] + 1), -load[g]))
                active[pool.submit(render_once, run, gpu, caps[run])] = (run, gpu)
                load[gpu] += 1
                free[gpu] -= 4096
            counts = Counter(
                "valid"
                if m.get("render_success")
                else "quality"
                if m.get("failure_class") == "quality"
                else "infrastructure_exhausted"
                if r in exhausted
                else "rendering"
                if r in busy
                else eligibility(m, caps[r])
                for r, m in manifests.items()
            )
            state.update(
                updated_at_utc=adapter.utc(),
                counts=dict(counts),
                active_render=len(active),
                active_gpus=dict(load),
                gpu_free_mib=free,
                active_runs=[str(r.relative_to(BASE)) for r, gpu in active.values()],
            )
            if counts["valid"] + counts["quality"] == 100:
                state["status"] = "render_matrix_complete"
            elif (
                not active
                and exhausted
                and counts["valid"] + counts["quality"] + len(exhausted) == 100
            ):
                state["status"] = "blocked_render_budget"
            adapter.write_json(OUTPUT / "state.json", state)
            print(
                json.dumps(
                    {
                        k: state[k]
                        for k in (
                            "updated_at_utc",
                            "status",
                            "counts",
                            "active_render",
                            "active_gpus",
                        )
                    }
                ),
                flush=True,
            )
            if state["status"] != "running":
                break
            time.sleep(20)
    controller_guard.close()


if __name__ == "__main__":
    main()
