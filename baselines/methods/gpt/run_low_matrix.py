#!/usr/bin/env python3
"""Run only GPT-6 Astra Low generation/build/render with auditable states."""
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
import gzip
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
METHOD = "gpt6_astra_low"
sys.path.insert(0, str((ROOT / "methods")))
from baselines.methods.gpt.adapter_low import generate
from baselines.methods.gpt.adapter_low import confined
from baselines.methods.gpt.adapter_low import digest
from baselines.methods.gpt.adapter_low import write_json
from baselines.methods.gpt.adapter_low import utc
from baselines.methods.gpt.adapter_low import run_process


def validate(run):
    from PIL import Image
    import numpy as np

    problems, records = [], []
    for kind, count, resolution in [
        ("anchors", 8, (1280, 720)),
        ("sequence", 50, (512, 512)),
    ]:
        files = sorted((run / "renders" / kind).glob("rgb_*.png"))
        if len(files) != count:
            problems.append(f"{kind}: expected {count}, found {len(files)}")
        for path in files:
            with Image.open(path) as image:
                if image.size != resolution:
                    problems.append(f"{path.name}: wrong resolution")
                array = np.asarray(image.convert("RGB"), dtype=np.float32) / 255
            mean, std = float(array.mean()), float(array.std())
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
        payload = json.loads(cameras.read_text())
        if (
            len(payload.get("sequence", [])) != 50
            or len(payload.get("anchors", [])) != 8
        ):
            problems.append("Wrong camera count")
        if payload["path_planner"]["max_displacement_m"] < 0.5:
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
        result = subprocess.run(
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
        free = int(result.stdout.strip())
        if free >= min_free_mib:
            return free
        print(f"WAIT gpu={gpu} free_mib={free} required_mib={min_free_mib}", flush=True)
        time.sleep(15)


def compress_attempt_logs(logdir):
    compressed = {}
    for name in ("stdout.log", "stderr.log"):
        path = logdir / name
        if not path.exists():
            continue
        target = path.with_suffix(path.suffix + ".gz")
        temporary = target.with_suffix(target.suffix + ".tmp")
        with path.open("rb") as source, gzip.open(
            temporary, "wb", compresslevel=1
        ) as destination:
            shutil.copyfileobj(source, destination, length=1024 * 1024)
        temporary.replace(target)
        original_size = path.stat().st_size
        path.unlink()
        compressed[name] = {
            "path": str(target.name),
            "original_bytes": original_size,
            "compressed_bytes": target.stat().st_size,
            "sha256": digest(target),
        }
    return compressed


def render_run(run, gpu, build_only=False):
    manifest_path = run / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    renderer = ROOT / "methods/gpt/tools/blender_render_gpt.py"
    renderer_hash = digest(renderer)
    if (run / "SUCCESS").exists():
        if manifest.get("renderer_sha256") != renderer_hash:
            raise RuntimeError(
                "Successful render has stale renderer; use a new data root"
            )
        return manifest
    if manifest.get("failure_class") == "quality" or not manifest.get(
        "generation_success"
    ):
        return manifest
    if digest(run / "scene/generated.py") != manifest["generated_code_sha256"]:
        raise RuntimeError("Generated scene code hash changed")
    manifest["renderer_sha256"] = renderer_hash
    manifest["shared_renderer_sha256"] = digest(
        (ROOT / "methods/sceneweaver/tools/blender_render_sceneweaver.py")
    )
    config = json.loads(
        ((ROOT / "methods/gpt/protocol/generation/gpt6_astra_low.json")).read_text()
    )
    (run / "tmp").mkdir(exist_ok=True)
    environment = dict(os.environ)
    environment.update(
        CUDA_VISIBLE_DEVICES="" if gpu is None else str(gpu),
        TMPDIR=str(run / "tmp"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    for phase in ["build"] if build_only else ["build", "render"]:
        if phase == "build" and manifest.get("build_success"):
            continue
        attempt_list = manifest.setdefault(phase + "_attempts", [])
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
                "build_timeout_s" if phase == "build" else "render_timeout_s"
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
            write_json(manifest_path, manifest)
            stdout_path, stderr_path = logdir / "stdout.log", logdir / "stderr.log"
            return_code, timed_out = run_process(
                command,
                run,
                stdout_path,
                stderr_path,
                limit,
                env=environment,
            )
            attempt.update(exit_code=return_code, timeout=timed_out, ended_at_utc=utc())
            logs = stdout_path.read_text(errors="replace") + stderr_path.read_text(
                errors="replace"
            )
            complete = (
                f"ASTRA_{phase.upper()}_COMPLETE" in logs
                and return_code == 0
                and not timed_out
            )
            resource_error = any(
                token in logs.lower()
                for token in (
                    "out of memory",
                    "cannot allocate memory",
                    "memoryerror",
                )
            )
            quality = not resource_error and (
                (phase == "build" and return_code == 11 and "generated.py" in logs)
                or any(
                    token in logs
                    for token in (
                        "No traversable camera cells",
                        "Traversable path too short",
                        "Generated scene contains",
                        "Generated scene has no mesh",
                    )
                )
            )
            tail = logs[-4000:]
            attempt["log_compression"] = compress_attempt_logs(logdir)
            if complete:
                manifest[phase + "_success"] = True
                manifest.update(failure_class=None, failure_reason=None)
                write_json(manifest_path, manifest)
                break
            manifest.update(
                failure_class="quality" if quality else "infrastructure",
                failure_reason=f"{phase} failed: {logdir.relative_to(run)}",
            )
            write_json(manifest_path, manifest)
            if quality:
                return manifest
            if (
                "bwrap:" in logs
                or "No CUDA/OPTIX" in logs
                or (return_code == 11 and not resource_error)
            ):
                raise RuntimeError(manifest["failure_reason"] + "\n" + tail)
            if index == 3:
                return manifest
        if not manifest.get(phase + "_success"):
            return manifest
    if build_only:
        return manifest
    result = validate(run)
    manifest["render_success"] = result["valid"]
    manifest["ended_at_utc"] = utc()
    manifest["exit_code"] = 0 if result["valid"] else 2
    if result["valid"]:
        (run / "SUCCESS").write_text(utc() + "\n")
    else:
        manifest.update(
            failure_class="quality", failure_reason="; ".join(result["problems"])
        )
    write_json(manifest_path, manifest)
    return manifest


def verify_formal_lock():
    lock_path = ROOT / "methods/gpt/protocol/generation/gpt6_astra_low.lock.json"
    if not lock_path.exists():
        raise RuntimeError("Formal Astra Low run requires a frozen pilot lock")
    lock = json.loads(lock_path.read_text())
    for relative, expected in lock["files_sha256"].items():
        if digest(ROOT / relative) != expected:
            raise RuntimeError("Frozen source changed: " + relative)


def task(spec, seed, data_root, gpu, phase):
    if shutil.disk_usage(ROOT).free < 50 * 1024**3:
        raise RuntimeError(
            "Less than 50 GiB free; pausing Astra Low without deleting artifacts"
        )
    if data_root == ROOT / "data/table2":
        verify_formal_lock()
    run = data_root / spec["domain"] / METHOD / spec["spec_id"] / f"seed_{seed}"
    print(f"START {spec['spec_id']} seed={seed} phase={phase} gpu={gpu}", flush=True)
    if phase in {"all", "generate"}:
        manifest = generate(spec, seed, data_root)
    if phase in {"all", "build", "render"}:
        manifest = render_run(run, gpu, build_only=phase == "build")
    print(
        f"DONE {spec['spec_id']} seed={seed} generated={manifest.get('generation_success')} "
        f"rendered={manifest.get('render_success')} failure={manifest.get('failure_class')}",
        flush=True,
    )
    return manifest


def pipeline(tasks, data_root, gpus, generators, builders=8):
    pending, ready = queue.Queue(), queue.Queue(maxsize=2 * len(gpus))
    built = queue.Queue(maxsize=2 * len(gpus))
    stop = threading.Event()
    generation_done, building_done = threading.Event(), threading.Event()
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


def select_tasks(domain, pilot, spec_id, seeds):
    tasks = []
    for current_domain in ["indoor", "urban"] if domain == "both" else [domain]:
        specs = [
            json.loads(line)
            for line in (ROOT / f"protocol/generation/{current_domain}_specs.jsonl")
            .read_text()
            .splitlines()
            if line
        ]
        if spec_id:
            specs = [spec for spec in specs if spec["spec_id"] == spec_id]
        elif pilot:
            specs = [spec for spec in specs if spec["spec_index"] % 5 == 0]
        for spec in specs:
            for seed in (
                seeds if seeds is not None else ([0, 1] if pilot else [0, 1, 2, 3])
            ):
                if seed not in range(4):
                    raise ValueError("Seed outside frozen set")
                tasks.append((spec, seed))
    if not tasks:
        raise ValueError("No matching tasks")
    return tasks


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
    parser.add_argument("--generators", type=int, default=0)
    parser.add_argument("--builders", type=int, default=None)
    parser.add_argument(
        "--data-root", type=Path, default=ROOT / "data/gpt6_astra_low_pilot"
    )
    args = parser.parse_args()
    data_root = confined(args.data_root)
    tasks = select_tasks(args.domain, args.pilot, args.spec_id, args.seeds)
    if args.generators:
        if args.phase != "all" or not 1 <= args.generators <= 8:
            raise ValueError(
                "Pipelining requires phase=all and 1..8 generation workers"
            )
        configured = json.loads(
            ((ROOT / "methods/gpt/protocol/generation/gpt6_astra_low.json")).read_text()
        )["build_workers"]
        results = pipeline(
            tasks, data_root, args.gpus, args.generators, args.builders or configured
        )
    else:

        def lane(index, gpu):
            return [
                task(spec, seed, data_root, gpu, args.phase)
                for spec, seed in tasks[index :: len(args.gpus)]
            ]

        with ThreadPoolExecutor(max_workers=len(args.gpus)) as pool:
            futures = [
                pool.submit(lane, index, gpu) for index, gpu in enumerate(args.gpus)
            ]
            results = []
            for future in as_completed(futures):
                results.extend(future.result())
    report = {
        "finished_at_utc": utc(),
        "data_root": str(data_root),
        "phase": args.phase,
        "runs": len(results),
        "generated": sum(bool(row.get("generation_success")) for row in results),
        "rendered": sum(bool(row.get("render_success")) for row in results),
    }
    suffix = (
        "pilot" if data_root == ROOT / "data/gpt6_astra_low_pilot" else data_root.name
    )
    write_json(
        ROOT / "results/gpt6_astra_low" / f"matrix_{suffix}_{args.phase}.json", report
    )
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
