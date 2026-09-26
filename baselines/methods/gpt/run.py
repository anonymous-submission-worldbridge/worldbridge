#!/usr/bin/env python3
"""Resume only GPT-6 Astra generation/build/render with auditable terminal states."""
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
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import shutil
import queue
import threading

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str((ROOT / "methods")))
from baselines.methods.gpt.adapter import generate
from baselines.methods.gpt.adapter import confined
from baselines.methods.gpt.adapter import digest
from baselines.methods.gpt.adapter import write_json
from baselines.methods.gpt.adapter import utc
from baselines.methods.gpt.adapter import run_process


def validate(run):
    from PIL import Image
    import numpy as np

    problems, records = [], []
    for kind, count, res in [("anchors", 8, (1280, 720)), ("sequence", 50, (512, 512))]:
        files = sorted((run / "renders" / kind).glob("rgb_*.png"))
        if len(files) != count:
            problems.append(f"{kind}: expected {count}, found {len(files)}")
        for path in files:
            with Image.open(path) as im:
                if im.size != res:
                    problems.append(f"{path.name}: wrong resolution")
                arr = np.asarray(im.convert("RGB"), dtype=np.float32) / 255
            mean, std = float(arr.mean()), float(arr.std())
            records.append(
                {"path": str(path.relative_to(run)), "mean": mean, "std": std}
            )
            if not 0.01 <= mean <= 0.99 or std < 0.01:
                problems.append(
                    str(path.relative_to(run)) + ": near black/white/constant"
                )
    cameras = run / "renders/sequence/cameras.json"
    if not cameras.exists():
        problems.append("Missing cameras.json")
    else:
        p = json.loads(cameras.read_text())
        if len(p.get("sequence", [])) != 50 or len(p.get("anchors", [])) != 8:
            problems.append("Wrong camera count")
        if p["path_planner"]["max_displacement_m"] < 0.5:
            problems.append("Insufficient camera translation")
    if not (run / "scene/scene.blend").exists():
        problems.append("Missing scene.blend")
    result = {
        "valid": not problems,
        "problems": problems,
        "images": records,
        "validated_at_utc": utc(),
    }
    write_json(run / "validation.json", result)
    return result


def wait_gpu(gpu, min_free_mib=8192):
    while True:
        r = subprocess.run(
            [
                "nvidia-smi",
                f"--id={gpu}",
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        free = int(r.stdout.strip())
        if free >= min_free_mib:
            return free
        print(f"WAIT gpu={gpu} free_mib={free} required_mib={min_free_mib}", flush=True)
        time.sleep(15)


def render_run(run, gpu, build_only=False):
    manifest_path = run / "run_manifest.json"
    m = json.loads(manifest_path.read_text())
    renderer = ROOT / "methods/gpt/tools/blender_render_gpt.py"
    renderer_hash = digest(renderer)
    if (run / "SUCCESS").exists():
        if m.get("renderer_sha256") != renderer_hash:
            raise RuntimeError(
                "Successful render has stale renderer; use a new pilot data root"
            )
        return m
    if m.get("failure_class") == "quality":
        return m
    if not m.get("generation_success"):
        return m
    if digest(run / "scene/generated.py") != m["generated_code_sha256"]:
        raise RuntimeError("Generated scene code hash changed")
    m["renderer_sha256"] = renderer_hash
    m["shared_renderer_sha256"] = digest(
        (ROOT / "methods/sceneweaver/tools/blender_render_sceneweaver.py")
    )
    config = json.loads(
        ((ROOT / "methods/gpt/protocol/generation/gpt6_astra.json")).read_text()
    )
    (run / "tmp").mkdir(exist_ok=True)
    env = dict(os.environ)
    env.update(
        CUDA_VISIBLE_DEVICES="" if gpu is None else str(gpu),
        TMPDIR=str(run / "tmp"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    for phase in ["build"] if build_only else ["build", "render"]:
        if phase == "build" and m.get("build_success"):
            continue
        attempt_list = m.setdefault(phase + "_attempts", [])
        for index in range(len(attempt_list) + 1, 4):
            admitted_free = (
                wait_gpu(gpu, config.get("min_render_free_mib", 8192))
                if phase == "render"
                else None
            )
            logdir = run / f"logs/{phase}_{index:02d}"
            logdir.mkdir(parents=True)
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
                str(
                    config.get(
                        "build_threads" if phase == "build" else "render_threads", 8
                    )
                ),
                "--python-exit-code",
                "11",
            ]
            if phase == "render":
                command.append(str(run / "scene/scene.blend"))
            command += [
                "--python",
                str(renderer),
                "--",
                "--run-dir",
                str(run),
                "--phase",
                phase,
            ]
            limit = config.get(
                "build_timeout_s" if phase == "build" else "render_timeout_s",
                7200 if phase == "build" else 1800,
            )
            attempt = {
                "index": index,
                "started_at_utc": utc(),
                "gpu": gpu,
                "command": command,
                "timeout_limit_s": limit,
                "gpu_admitted_free_mib": admitted_free,
                "gpu_policy": "remaining_memory_sharing",
            }
            attempt_list.append(attempt)
            write_json(manifest_path, m)
            rc, timeout = run_process(
                command,
                run,
                logdir / "stdout.log",
                logdir / "stderr.log",
                limit,
                env=env,
            )
            attempt.update(exit_code=rc, timeout=timeout, ended_at_utc=utc())
            logs = (logdir / "stdout.log").read_text() + (
                logdir / "stderr.log"
            ).read_text()
            complete = (
                f"ASTRA_{phase.upper()}_COMPLETE" in logs and rc == 0 and not timeout
            )
            if complete:
                m[phase + "_success"] = True
                m.update(failure_class=None, failure_reason=None)
                write_json(manifest_path, m)
                break
            resource_error = any(
                token in logs.lower()
                for token in ["out of memory", "cannot allocate memory", "memoryerror"]
            )
            quality = not resource_error and (
                (phase == "build" and rc == 11 and "generated.py" in logs)
                or any(
                    s in logs
                    for s in (
                        "No traversable camera cells",
                        "Traversable path too short",
                        "Generated scene contains",
                        "Generated scene has no mesh",
                    )
                )
            )
            m.update(
                failure_class="quality" if quality else "infrastructure",
                failure_reason=f"{phase} failed: {logdir.relative_to(run)}",
            )
            write_json(manifest_path, m)
            if quality:
                return m
            # A local setup failure should stop the queue without consuming all retries.
            if (
                "bwrap:" in logs
                or "No CUDA/OPTIX" in logs
                or (rc == 11 and not resource_error)
            ):
                raise RuntimeError(m["failure_reason"] + "\n" + logs[-2500:])
            if index == 3:
                return m
        if not m.get(phase + "_success"):
            return m
    if build_only:
        return m
    result = validate(run)
    m["render_success"] = result["valid"]
    m["ended_at_utc"] = utc()
    m["exit_code"] = 0 if result["valid"] else 2
    if result["valid"]:
        (run / "SUCCESS").write_text(utc() + "\n")
    else:
        m.update(failure_class="quality", failure_reason="; ".join(result["problems"]))
    write_json(manifest_path, m)
    return m


def task(spec, seed, data_root, gpu, phase):
    if shutil.disk_usage(ROOT).free < 50 * 1024**3:
        raise RuntimeError(
            "Less than 50 GiB free; pausing new Astra work without deleting artifacts"
        )
    if data_root == ROOT / "data/table2":
        lock = json.loads(
            (
                (ROOT / "methods/gpt/protocol/generation/gpt6_astra.lock.json")
            ).read_text()
        )
        for relative, expected in lock["files_sha256"].items():
            if digest(ROOT / relative) != expected:
                raise RuntimeError("Frozen source changed: " + relative)
    run = data_root / spec["domain"] / "gpt6_astra" / spec["spec_id"] / f"seed_{seed}"
    print(f'START {spec["spec_id"]} seed={seed} phase={phase} gpu={gpu}', flush=True)
    if phase in {"all", "generate"}:
        m = generate(spec, seed, data_root)
    if phase in {"all", "build", "render"}:
        m = render_run(run, gpu, build_only=phase == "build")
    print(
        f'DONE {spec["spec_id"]} seed={seed} generated={m.get("generation_success")} rendered={m.get("render_success")} failure={m.get("failure_class")}',
        flush=True,
    )
    return m


def pipeline(tasks, data_root, gpus, generators, builders=8):
    """Independent bounded generation, CPU construction, and shared GPU lanes."""
    pending = queue.Queue()
    ready = queue.Queue(maxsize=2 * len(gpus))
    built = queue.Queue(maxsize=2 * len(gpus))
    stop = threading.Event()
    generation_done = threading.Event()
    building_done = threading.Event()
    results, errors = [], []
    for item in tasks:
        pending.put(item)

    def producer():
        try:
            while not stop.is_set():
                try:
                    spec, seed = pending.get_nowait()
                except queue.Empty:
                    return
                result = task(spec, seed, data_root, None, "generate")
                if result.get("failure_class") in {"infrastructure", "access_blocked"}:
                    raise RuntimeError(
                        "Generation infrastructure unresolved; pausing new work"
                    )
                if (
                    not result.get("generation_success")
                    or result.get("failure_class") == "quality"
                ):
                    results.append(result)
                    continue
                while not stop.is_set():
                    try:
                        ready.put((spec, seed), timeout=1)
                        break
                    except queue.Full:
                        pass
        except Exception as exc:
            errors.append(exc)
            stop.set()

    def consumer(gpu, phase, incoming, upstream_done, outgoing=None):
        try:
            while not stop.is_set():
                try:
                    spec, seed = incoming.get(timeout=1)
                except queue.Empty:
                    if upstream_done.is_set():
                        return
                    continue
                result = task(spec, seed, data_root, gpu, phase)
                if result.get("failure_class") in {"infrastructure", "access_blocked"}:
                    raise RuntimeError(
                        phase + " infrastructure unresolved; pausing new work"
                    )
                if outgoing is None or result.get("failure_class") == "quality":
                    results.append(result)
                else:
                    if not result.get("build_success"):
                        raise RuntimeError(
                            "CPU builder returned without a terminal result"
                        )
                    while not stop.is_set():
                        try:
                            outgoing.put((spec, seed), timeout=1)
                            break
                        except queue.Full:
                            pass
        except Exception as exc:
            errors.append(exc)
            stop.set()

    producers = [threading.Thread(target=producer) for _ in range(generators)]
    constructors = [
        threading.Thread(
            target=consumer, args=(None, "build", ready, generation_done, built)
        )
        for _ in range(builders)
    ]
    consumers = [
        threading.Thread(target=consumer, args=(gpu, "render", built, building_done))
        for gpu in gpus
    ]
    for thread in consumers + constructors + producers:
        thread.start()
    for thread in producers:
        thread.join()
    generation_done.set()
    for thread in constructors:
        thread.join()
    building_done.set()
    for thread in consumers:
        thread.join()
    if errors:
        raise RuntimeError("Pipeline paused; completed artifacts retained") from errors[
            0
        ]
    if len(results) != len(tasks):
        raise RuntimeError("Pipeline lost task accounting")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase", choices=["all", "generate", "build", "render"], default="all"
    )
    parser.add_argument("--domain", choices=["indoor", "urban", "both"], default="both")
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--spec-id")
    parser.add_argument("--seeds", type=int, nargs="+", default=None)
    parser.add_argument("--gpus", type=int, nargs="+", default=[0])
    parser.add_argument(
        "--generators",
        type=int,
        default=0,
        help="Separate code generation concurrency; 0 uses sequential GPU lanes",
    )
    parser.add_argument(
        "--data-root", type=Path, default=ROOT / "data/gpt6_astra_pilot"
    )
    parser.add_argument("--refresh-pilot-renderer", action="store_true")
    parser.add_argument("--refresh-pilot-build-budget", action="store_true")
    parser.add_argument("--inspect-pilot-workers", action="store_true")
    parser.add_argument("--adopt-pilot-workers", action="store_true")
    parser.add_argument("--adopt-parent-pid", type=int)
    parser.add_argument("--pilot-build-timeout", type=int, choices=[21600])
    parser.add_argument("--complete-after-pilot", action="store_true")
    args = parser.parse_args()
    if args.complete_after_pilot:
        sys.path.insert(0, str(ROOT / "tools"))
        from baselines.methods.gpt.tools.supervise_gpt import supervise

        supervise(args.gpus, args.generators or 4)
        return
    if args.inspect_pilot_workers or args.adopt_pilot_workers:
        sys.path.insert(0, str(ROOT / "tools"))
        from baselines.methods.gpt.tools.migrate_gpt_scheduler import inspect_old
        from baselines.methods.gpt.tools.migrate_gpt_scheduler import adopt

        if args.inspect_pilot_workers:
            print(json.dumps(inspect_old(args.adopt_parent_pid), indent=2))
        else:
            if args.pilot_build_timeout:
                config = json.loads(
                    (
                        (ROOT / "methods/gpt/protocol/generation/gpt6_astra.json")
                    ).read_text()
                )
                if (
                    config.get("status") == "formal_frozen"
                    or config.get("build_timeout_s") != args.pilot_build_timeout
                ):
                    raise RuntimeError(
                        "Budget revision must match the unfrozen pilot configuration"
                    )
            adopt(args.gpus, args.adopt_parent_pid, args.pilot_build_timeout)
        return
    data_root = confined(args.data_root)
    tasks = []
    for domain in ["indoor", "urban"] if args.domain == "both" else [args.domain]:
        specs = [
            json.loads(l)
            for l in (ROOT / f"protocol/generation/{domain}_specs.jsonl")
            .read_text()
            .splitlines()
            if l
        ]
        if args.spec_id:
            specs = [s for s in specs if s["spec_id"] == args.spec_id]
        elif args.pilot:
            specs = [s for s in specs if s["spec_index"] % 5 == 0]
        for spec in specs:
            for seed in (
                args.seeds
                if args.seeds is not None
                else ([0, 1] if args.pilot else [0, 1, 2, 3])
            ):
                if seed not in range(4):
                    raise ValueError("Seed outside frozen set")
                tasks.append((spec, seed))
    if not tasks:
        raise ValueError("No matching tasks")
    if args.refresh_pilot_build_budget:
        if data_root != ROOT / "data/gpt6_astra_pilot" or args.phase != "render":
            raise ValueError(
                "Build budget revision is restricted to existing pilot code"
            )
        for spec, seed in tasks:
            run = (
                data_root
                / spec["domain"]
                / "gpt6_astra"
                / spec["spec_id"]
                / f"seed_{seed}"
            )
            path = run / "run_manifest.json"
            m = json.loads(path.read_text())
            attempts = m.get("build_attempts", [])
            if m.get("build_success") or m.get("failure_class") != "infrastructure":
                continue
            if not attempts or not all(a.get("timeout") for a in attempts):
                raise RuntimeError(
                    "Budget revision cannot clear a non-timeout failure: " + str(run)
                )
            revision = run / "pilot_build_history" / utc().replace(":", "-")
            revision.mkdir(parents=True)
            shutil.copy2(path, revision / "run_manifest.json")
            for log in sorted((run / "logs").glob("build_*")):
                shutil.move(str(log), str(revision / log.name))
            for name in ["scene.blend", "scene.blend1", "geometry.json"]:
                if (run / "scene" / name).exists():
                    shutil.move(str(run / "scene" / name), str(revision / name))
            m.setdefault("pilot_build_revisions", []).append(
                {
                    "reason": "pilot CPU build limit 1800s to 7200s; same generated code",
                    "archive": str(revision.relative_to(run)),
                    "previous_attempt_count": len(attempts),
                }
            )
            m.update(build_attempts=[], failure_class=None, failure_reason=None)
            write_json(path, m)
    if args.refresh_pilot_renderer:
        if data_root != ROOT / "data/gpt6_astra_pilot" or args.phase != "render":
            raise ValueError("Renderer refresh is restricted to pilot render-only work")
        for spec, seed in tasks:
            run = (
                data_root
                / spec["domain"]
                / "gpt6_astra"
                / spec["spec_id"]
                / f"seed_{seed}"
            )
            path = run / "run_manifest.json"
            m = json.loads(path.read_text())
            if not m.get("build_success"):
                continue
            revision = run / "pilot_render_history" / utc().replace(":", "-")
            revision.mkdir(parents=True)
            shutil.copy2(path, revision / "run_manifest.json")
            for name in ["renders", "validation.json", "SUCCESS", "metrics"]:
                if (run / name).exists():
                    shutil.move(str(run / name), str(revision / name))
            (revision / "logs").mkdir()
            for log in sorted((run / "logs").glob("render_*")):
                shutil.move(str(log), str(revision / "logs" / log.name))
            if (run / "logs/worldscore.log").exists():
                shutil.move(
                    str(run / "logs/worldscore.log"),
                    str(revision / "logs/worldscore.log"),
                )
            m.update(
                render_success=False,
                render_attempts=[],
                failure_class=None,
                failure_reason=None,
            )
            m.setdefault("pilot_revisions", []).append(
                {
                    "reason": "uniform pilot camera implementation revision; same generated scene",
                    "archive": str(revision.relative_to(run)),
                }
            )
            write_json(path, m)

    # One sequential lane per GPU; concurrency never runs two renders on one device.
    def lane(index, gpu):
        return [
            task(spec, seed, data_root, gpu, args.phase)
            for spec, seed in tasks[index :: len(args.gpus)]
        ]

    if args.generators:
        if args.phase != "all" or not 1 <= args.generators <= 4:
            raise ValueError(
                "Pipelining requires phase=all and 1..4 generation workers"
            )
        builders = json.loads(
            ((ROOT / "methods/gpt/protocol/generation/gpt6_astra.json")).read_text()
        ).get("build_workers", 8)
        results = pipeline(tasks, data_root, args.gpus, args.generators, builders)
    else:
        with ThreadPoolExecutor(max_workers=len(args.gpus)) as pool:
            futures = [pool.submit(lane, i, gpu) for i, gpu in enumerate(args.gpus)]
            results = []
            for future in as_completed(futures):
                results.extend(future.result())
    report = {
        "finished_at_utc": utc(),
        "data_root": str(data_root),
        "phase": args.phase,
        "runs": len(results),
        "generated": sum(bool(m.get("generation_success")) for m in results),
        "rendered": sum(bool(m.get("render_success")) for m in results),
    }
    write_json(
        ROOT / "results/gpt6_astra" / f"matrix_{data_root.name}_{args.phase}.json",
        report,
    )
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
