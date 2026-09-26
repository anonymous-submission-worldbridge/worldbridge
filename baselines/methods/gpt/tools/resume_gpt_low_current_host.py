#!/usr/bin/env python3
"""Resume the migrated Astra Low Urban tail and exact render recoveries."""
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
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path[:0] = [str(ROOT), str((ROOT / "methods")), str(ROOT / "tools")]

import baselines.methods.gpt.adapter_low as adapter
import baselines.methods.gpt.run_low_matrix as matrix
import baselines.methods.gpt.tools.resume_gpt_low_gpu_recovery as recovery

METHOD = "gpt6_astra_low"
AMENDMENT = (
    ROOT
    / "methods/gpt/protocol/generation/gpt6_astra_low_render_recovery_20260914.json"
)
OUTPUT = ROOT / "results/gpt6_astra_low/current_host_recovery_20260914"
INTERRUPTED = (
    ("urban_leisure_civic_four_way_20", 1),
    ("urban_leisure_civic_four_way_20", 2),
    ("urban_leisure_civic_main_side_22", 1),
)
EXHAUSTED = (
    ("urban_mixed_use_irregular_14", 1),
    ("urban_park_edge_main_side_17", 0),
)
TAIL_SPECS = tuple(range(20, 25))


def run_dir(spec_id: str, seed: int) -> Path:
    return ROOT / "data/table2/urban" / METHOD / spec_id / f"seed_{seed}"


def configure_recovery() -> None:
    matrix.wait_gpu = recovery.recovery_wait_gpu
    matrix.run_process = recovery.recovery_run_process
    matrix.shutil.disk_usage = recovery.recovery_disk_usage
    matrix.verify_formal_lock = recovery.recovery_verify_formal_lock
    recovery.recovery_verify_formal_lock()


def reconcile_interruptions() -> list[str]:
    reconciled = []
    for spec_id, seed in INTERRUPTED:
        run = run_dir(spec_id, seed)
        path = run / "run_manifest.json"
        manifest = json.loads(path.read_text())
        attempts = manifest.get("render_attempts", [])
        if manifest.get("render_success") or manifest.get("failure_class") == "quality":
            continue
        if not attempts or attempts[-1].get("ended_at_utc"):
            continue
        backup = OUTPUT / "interrupted_previous" / spec_id / f"seed_{seed}"
        backup.mkdir(parents=True, exist_ok=True)
        target = backup / "run_manifest.json"
        if not target.exists():
            shutil.copy2(path, target)
        attempts[-1].update(
            ended_at_utc=adapter.utc(),
            exit_code=None,
            timeout=False,
            infrastructure_interruption=(
                "The migrated controller and worker disappeared; the true exit "
                "status is unavailable. This is not a quality failure."
            ),
            interruption_reconciled_by=str(OUTPUT.relative_to(ROOT)),
        )
        manifest.update(
            failure_class="infrastructure",
            failure_reason="Render interrupted by controller exit during machine migration",
        )
        adapter.write_json(path, manifest)
        reconciled.append(f"{spec_id}/seed_{seed}")
    return reconciled


def tail_tasks():
    tasks = matrix.select_tasks("urban", False, None, None)
    return [item for item in tasks if int(item[0]["spec_index"]) in TAIL_SPECS]


def finalize_completed_renders(tasks) -> list[str]:
    """Finish validation when Blender completed but the controller then died."""
    finalized = []
    for spec, seed in tasks:
        run = run_dir(spec["spec_id"], seed)
        path = run / "run_manifest.json"
        if not path.exists() or (run / "SUCCESS").exists():
            continue
        manifest = json.loads(path.read_text())
        attempts = manifest.get("render_attempts", [])
        if (
            not manifest.get("render_success")
            or not attempts
            or not attempts[-1].get("ended_at_utc")
        ):
            continue
        result = matrix.validate(run)
        manifest["render_success"] = result["valid"]
        manifest["ended_at_utc"] = adapter.utc()
        manifest["exit_code"] = 0 if result["valid"] else 2
        manifest["post_render_validation_recovery"] = {
            "at_utc": adapter.utc(),
            "reason": "Blender completed before the prior controller lost its NumPy validation environment",
            "recovery_controller": str(Path(__file__).relative_to(ROOT)),
        }
        if result["valid"]:
            manifest.update(failure_class=None, failure_reason=None)
            (run / "SUCCESS").write_text(adapter.utc() + "\n")
        else:
            manifest.update(
                failure_class="quality", failure_reason="; ".join(result["problems"])
            )
        adapter.write_json(path, manifest)
        finalized.append(f"{spec['spec_id']}/seed_{seed}")
    return finalized


def resume_tail(gpu: int, generators: int, builders: int) -> dict:
    configure_recovery()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    reconciled = reconcile_interruptions()
    tasks = tail_tasks()
    finalized = finalize_completed_renders(tasks)
    data_root = ROOT / "data/table2"

    # The original pipeline treats any carried render infrastructure status as
    # a generation failure, even when generation_success is already true. Use
    # the same frozen task implementation with explicit stage-aware queues.
    def manifest_for(spec, seed):
        path = run_dir(spec["spec_id"], seed) / "run_manifest.json"
        return json.loads(path.read_text()) if path.exists() else None

    generation_tasks = []
    for spec, seed in tasks:
        manifest = manifest_for(spec, seed)
        if manifest is None or (
            not manifest.get("generation_success")
            and manifest.get("failure_class") != "quality"
        ):
            generation_tasks.append((spec, seed))
    with ThreadPoolExecutor(max_workers=generators) as pool:
        futures = {
            pool.submit(matrix.task, spec, seed, data_root, None, "generate"): (
                spec,
                seed,
            )
            for spec, seed in generation_tasks
        }
        for future in as_completed(futures):
            result = future.result()
            if result.get("failure_class") in {"infrastructure", "access_blocked"}:
                raise RuntimeError(
                    "Generation infrastructure unresolved; artifacts retained"
                )

    build_tasks = []
    for spec, seed in tasks:
        manifest = manifest_for(spec, seed)
        if (
            manifest
            and manifest.get("generation_success")
            and not manifest.get("build_success")
            and manifest.get("failure_class") != "quality"
        ):
            build_tasks.append((spec, seed))
    with ThreadPoolExecutor(max_workers=builders) as pool:
        futures = {
            pool.submit(matrix.task, spec, seed, data_root, None, "build"): (spec, seed)
            for spec, seed in build_tasks
        }
        for future in as_completed(futures):
            result = future.result()
            if result.get("failure_class") in {"infrastructure", "access_blocked"}:
                raise RuntimeError(
                    "Build infrastructure unresolved; artifacts retained"
                )

    results = []
    for spec, seed in tasks:
        manifest = manifest_for(spec, seed)
        if (
            manifest
            and manifest.get("build_success")
            and not manifest.get("render_success")
            and manifest.get("failure_class") != "quality"
        ):
            manifest = matrix.task(spec, seed, data_root, gpu, "render")
        results.append(manifest or {})
    report = {
        "status": "complete",
        "ended_at_utc": adapter.utc(),
        "gpu": gpu,
        "task_count": len(tasks),
        "reconciled_interruptions": reconciled,
        "finalized_completed_renders": finalized,
        "rendered": sum(bool(row.get("render_success")) for row in results),
        "quality_failures": sum(
            row.get("failure_class") == "quality" for row in results
        ),
        "infrastructure_failures": sum(
            row.get("failure_class") == "infrastructure" for row in results
        ),
    }
    adapter.write_json(OUTPUT / "tail.json", report)
    print(json.dumps(report, indent=2), flush=True)
    return report


def render_extra_once(run: Path, gpu: int) -> dict:
    configure_recovery()
    if shutil.disk_usage(ROOT).free < recovery.MIN_RECOVERY_DISK_FREE_BYTES:
        raise RuntimeError("Less than 20 GiB free; refusing recovery")
    guard_path = run / "astra_low_recovery.lock"
    guard = guard_path.open("a")
    fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        path = run / "run_manifest.json"
        manifest = json.loads(path.read_text())
        attempts = manifest.get("render_attempts", [])
        if manifest.get("render_success") or (run / "SUCCESS").exists():
            return manifest
        if manifest.get("failure_class") == "quality":
            raise RuntimeError("Quality failures must not be retried: " + str(run))
        if not manifest.get("build_success") or len(attempts) != 3:
            raise RuntimeError(
                "Expected exactly three exhausted render attempts: " + str(run)
            )
        if any(not attempt.get("ended_at_utc") for attempt in attempts):
            raise RuntimeError("Cannot retry an open attempt: " + str(run))
        renderer = ROOT / "methods/gpt/tools/blender_render_gpt.py"
        if (
            adapter.digest(run / "scene/generated.py")
            != manifest["generated_code_sha256"]
        ):
            raise RuntimeError("Generated code changed: " + str(run))
        if manifest.get("renderer_sha256") != adapter.digest(renderer):
            raise RuntimeError("Renderer changed: " + str(run))
        backup = OUTPUT / "exhausted_previous" / run.parent.name / run.name
        backup.mkdir(parents=True, exist_ok=True)
        target = backup / "run_manifest.json"
        if not target.exists():
            shutil.copy2(path, target)
        admitted = recovery.recovery_wait_gpu(gpu, recovery.MIN_RECOVERY_FREE_MIB)
        index = 4
        logdir = run / f"logs/render_{index:02d}"
        logdir.mkdir(parents=True, exist_ok=False)
        config = json.loads(
            ((ROOT / "methods/gpt/protocol/generation/gpt6_astra_low.json")).read_text()
        )
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
        attempt = {
            "index": index,
            "started_at_utc": adapter.utc(),
            "gpu": gpu,
            "command": command,
            "timeout_limit_s": 7200,
            "previous_protocol_timeout_s": 1800,
            "gpu_admitted_free_mib": admitted,
            "gpu_policy": "remaining_memory_sharing",
            "resource_amendment": str(AMENDMENT.relative_to(ROOT)),
            "original_attempts_preserved": True,
        }
        attempts.append(attempt)
        manifest["render_budget_revision"] = {
            "amendment": str(AMENDMENT.relative_to(ROOT)),
            "timeout_limit_s": 7200,
            "max_attempts": 4,
            "changes": "resources_only",
        }
        adapter.write_json(path, manifest)
        environment = dict(
            os.environ,
            CUDA_VISIBLE_DEVICES=str(gpu),
            TMPDIR=str(run / "tmp"),
            PYTHONDONTWRITEBYTECODE="1",
        )
        stdout = logdir / "stdout.log"
        stderr = logdir / "stderr.log"
        print("RECOVERY_START", run.parent.name, run.name, "gpu", gpu, flush=True)
        return_code, timed_out = recovery.recovery_run_process(
            command,
            run,
            stdout,
            stderr,
            7200,
            env=environment,
        )
        attempt.update(
            exit_code=return_code, timeout=timed_out, ended_at_utc=adapter.utc()
        )
        logs = stdout.read_text(errors="replace") + stderr.read_text(errors="replace")
        complete = (
            "ASTRA_RENDER_COMPLETE" in logs and return_code == 0 and not timed_out
        )
        quality = any(
            token in logs
            for token in (
                "No traversable camera cells",
                "Traversable path too short",
                "Generated scene contains",
                "Generated scene has no mesh",
            )
        )
        attempt["log_compression"] = matrix.compress_attempt_logs(logdir)
        if complete:
            result = matrix.validate(run)
            manifest["render_success"] = result["valid"]
            manifest["ended_at_utc"] = adapter.utc()
            manifest["exit_code"] = 0 if result["valid"] else 2
            if result["valid"]:
                manifest.update(failure_class=None, failure_reason=None)
                (run / "SUCCESS").write_text(adapter.utc() + "\n")
            else:
                manifest.update(
                    failure_class="quality",
                    failure_reason="; ".join(result["problems"]),
                )
        else:
            manifest.update(
                failure_class="quality" if quality else "infrastructure",
                failure_reason=f"render failed: {logdir.relative_to(run)}",
            )
        adapter.write_json(path, manifest)
        print(
            "RECOVERY_END",
            run.parent.name,
            run.name,
            "success",
            manifest.get("render_success"),
            "failure",
            manifest.get("failure_class"),
            flush=True,
        )
        return manifest
    finally:
        guard.close()


def resume_exhausted(gpu: int) -> dict:
    configure_recovery()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    results = []
    for spec_id, seed in EXHAUSTED:
        result = render_extra_once(run_dir(spec_id, seed), gpu)
        results.append(
            {
                "spec_id": spec_id,
                "seed": seed,
                "render_success": bool(result.get("render_success")),
                "failure_class": result.get("failure_class"),
            }
        )
    report = {
        "status": "complete",
        "ended_at_utc": adapter.utc(),
        "gpu": gpu,
        "runs": results,
    }
    adapter.write_json(OUTPUT / "exhausted.json", report)
    print(json.dumps(report, indent=2), flush=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("tail", "exhausted"))
    parser.add_argument("--gpu", type=int, default=4)
    parser.add_argument("--generators", type=int, default=2)
    parser.add_argument("--builders", type=int, default=4)
    args = parser.parse_args()
    if args.phase == "tail":
        resume_tail(args.gpu, args.generators, args.builders)
    else:
        resume_exhausted(args.gpu)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
