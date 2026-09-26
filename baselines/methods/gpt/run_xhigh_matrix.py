#!/usr/bin/env python3
"""Run only the GPT-6 Astra Extra High Table-2 generation/build/render matrix."""
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
import queue
import shutil
import subprocess
import sys
import threading
import time

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str((ROOT / "methods")))
from baselines.methods.gpt.adapter import confined
from baselines.methods.gpt.adapter import digest
from baselines.methods.gpt.adapter import run_process
from baselines.methods.gpt.adapter import utc
from baselines.methods.gpt.adapter import write_json
from baselines.methods.gpt.adapter_xhigh import METHOD
from baselines.methods.gpt.adapter_xhigh import generate

CONFIG = ROOT / "methods/gpt/protocol/generation/gpt6_astra_xhigh.json"
LOCK = ROOT / "methods/gpt/protocol/generation/gpt6_astra_xhigh.lock.json"


def verify_formal_lock() -> None:
    lock = json.loads(LOCK.read_text())
    for relative, expected in lock["files_sha256"].items():
        if digest(ROOT / relative) != expected:
            raise RuntimeError("Frozen Extra High source changed: " + relative)


def validate(run: Path) -> dict:
    from PIL import Image
    import numpy as np

    problems, records = [], []
    for kind, count, resolution in (
        ("anchors", 8, (1280, 720)),
        ("sequence", 50, (512, 512)),
    ):
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
        if payload.get("path_planner", {}).get("max_displacement_m", 0) < 0.5:
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


def wait_gpu(gpu: int, minimum_free_mib: int) -> int:
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
        if free >= minimum_free_mib:
            return free
        print(
            f"XHIGH_WAIT gpu={gpu} free_mib={free} required_mib={minimum_free_mib}",
            flush=True,
        )
        time.sleep(15)


def render_run(run: Path, gpu: int | None, build_only: bool = False) -> dict:
    manifest_path = run / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    renderer = ROOT / "methods/gpt/tools/blender_render_gpt.py"
    renderer_hash = digest(renderer)
    if (run / "SUCCESS").exists():
        if manifest.get("renderer_sha256") != renderer_hash:
            raise RuntimeError(
                "Successful Extra High render has stale shared renderer: " + str(run)
            )
        return manifest
    if manifest.get("failure_class") == "quality" or not manifest.get(
        "generation_success"
    ):
        return manifest
    if digest(run / "scene/generated.py") != manifest["generated_code_sha256"]:
        raise RuntimeError("Generated scene code hash changed: " + str(run))
    config = json.loads(CONFIG.read_text())
    manifest["renderer_sha256"] = renderer_hash
    manifest["shared_renderer_sha256"] = digest(
        (ROOT / "methods/sceneweaver/tools/blender_render_sceneweaver.py")
    )
    (run / "tmp").mkdir(exist_ok=True)
    env = dict(os.environ)
    env.update(
        CUDA_VISIBLE_DEVICES="" if gpu is None else str(gpu),
        TMPDIR=str(run / "tmp"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    for phase in ["build"] if build_only else ["build", "render"]:
        if manifest.get(phase + "_success"):
            continue
        attempts = manifest.setdefault(phase + "_attempts", [])
        for index in range(len(attempts) + 1, 4):
            admitted = (
                wait_gpu(gpu, config["min_render_free_mib"])
                if phase == "render"
                else None
            )
            log_dir = run / f"logs/{phase}_{index:02d}"
            log_dir.mkdir(parents=True, exist_ok=False)
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
                str(config["build_threads" if phase == "build" else "render_threads"]),
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
            limit = config[
                "build_timeout_s" if phase == "build" else "render_timeout_s"
            ]
            attempt = {
                "index": index,
                "started_at_utc": utc(),
                "gpu": gpu,
                "command": command,
                "timeout_limit_s": limit,
                "gpu_admitted_free_mib": admitted,
                "gpu_policy": "remaining_memory_sharing",
            }
            attempts.append(attempt)
            write_json(manifest_path, manifest)
            code, timed_out = run_process(
                command,
                run,
                log_dir / "stdout.log",
                log_dir / "stderr.log",
                limit,
                env=env,
            )
            attempt.update(exit_code=code, timeout=timed_out, ended_at_utc=utc())
            logs = (log_dir / "stdout.log").read_text() + (
                log_dir / "stderr.log"
            ).read_text()
            complete = (
                f"ASTRA_{phase.upper()}_COMPLETE" in logs
                and code == 0
                and not timed_out
            )
            if complete:
                manifest[phase + "_success"] = True
                manifest.update(failure_class=None, failure_reason=None)
                write_json(manifest_path, manifest)
                break
            resource_error = any(
                token in logs.lower()
                for token in ("out of memory", "cannot allocate memory", "memoryerror")
            )
            quality = not resource_error and (
                (phase == "build" and code == 11 and "generated.py" in logs)
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
            manifest.update(
                failure_class="quality" if quality else "infrastructure",
                failure_reason=f"{phase} failed: {log_dir.relative_to(run)}",
            )
            write_json(manifest_path, manifest)
            if quality:
                return manifest
            if (
                "bwrap:" in logs
                or "No CUDA/OPTIX" in logs
                or (code == 11 and not resource_error)
            ):
                raise RuntimeError(manifest["failure_reason"] + "\n" + logs[-2500:])
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


def task(spec: dict, seed: int, data_root: Path, gpu: int | None, phase: str) -> dict:
    config = json.loads(CONFIG.read_text())
    if shutil.disk_usage(ROOT).free < config["disk_stop_free_gib"] * 1024**3:
        raise RuntimeError(
            "Extra High disk safety threshold reached; no new task started"
        )
    if data_root == ROOT / "data/table2":
        verify_formal_lock()
    run = data_root / spec["domain"] / METHOD / spec["spec_id"] / f"seed_{seed}"
    print(
        f"XHIGH_START {spec['spec_id']} seed={seed} phase={phase} gpu={gpu}", flush=True
    )
    manifest = (
        generate(spec, seed, data_root)
        if phase in {"all", "generate"}
        else json.loads((run / "run_manifest.json").read_text())
    )
    if phase in {"all", "build", "render"}:
        manifest = render_run(run, gpu, build_only=phase == "build")
    print(
        f"XHIGH_DONE {spec['spec_id']} seed={seed} generated={manifest.get('generation_success')} "
        f"rendered={manifest.get('render_success')} failure={manifest.get('failure_class')}",
        flush=True,
    )
    return manifest


def pipeline(
    tasks: list[tuple[dict, int]],
    data_root: Path,
    gpus: list[int],
    generators: int,
    builders: int,
) -> list[dict]:
    pending, ready, built = (
        queue.Queue(),
        queue.Queue(maxsize=2 * len(gpus)),
        queue.Queue(maxsize=2 * len(gpus)),
    )
    for item in tasks:
        pending.put(item)
    stop, generation_done, building_done = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    results, errors = [], []
    result_lock = threading.Lock()

    def put_result(value: dict) -> None:
        with result_lock:
            results.append(value)

    def producer() -> None:
        try:
            while not stop.is_set():
                try:
                    spec, seed = pending.get_nowait()
                except queue.Empty:
                    return
                value = task(spec, seed, data_root, None, "generate")
                if value.get("failure_class") in {"infrastructure", "access_blocked"}:
                    raise RuntimeError(
                        "Extra High generation infrastructure unresolved"
                    )
                if (
                    not value.get("generation_success")
                    or value.get("failure_class") == "quality"
                ):
                    put_result(value)
                else:
                    while not stop.is_set():
                        try:
                            ready.put((spec, seed), timeout=1)
                            break
                        except queue.Full:
                            pass
        except Exception as exc:
            errors.append(exc)
            stop.set()

    def consumer(
        gpu: int | None,
        phase: str,
        incoming: queue.Queue,
        upstream_done: threading.Event,
        outgoing: queue.Queue | None = None,
    ) -> None:
        try:
            while not stop.is_set():
                try:
                    spec, seed = incoming.get(timeout=1)
                except queue.Empty:
                    if upstream_done.is_set():
                        return
                    continue
                value = task(spec, seed, data_root, gpu, phase)
                if value.get("failure_class") in {"infrastructure", "access_blocked"}:
                    raise RuntimeError(f"Extra High {phase} infrastructure unresolved")
                if outgoing is None or value.get("failure_class") == "quality":
                    put_result(value)
                else:
                    if not value.get("build_success"):
                        raise RuntimeError(
                            "Extra High builder returned without terminal state"
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

    producer_threads = [
        threading.Thread(target=producer, name=f"xhigh-generate-{i}")
        for i in range(generators)
    ]
    builder_threads = [
        threading.Thread(
            target=consumer,
            args=(None, "build", ready, generation_done, built),
            name=f"xhigh-build-{i}",
        )
        for i in range(builders)
    ]
    renderer_threads = [
        threading.Thread(
            target=consumer,
            args=(gpu, "render", built, building_done),
            name=f"xhigh-render-{gpu}",
        )
        for gpu in gpus
    ]
    for thread in renderer_threads + builder_threads + producer_threads:
        thread.start()
    for thread in producer_threads:
        thread.join()
    generation_done.set()
    for thread in builder_threads:
        thread.join()
    building_done.set()
    for thread in renderer_threads:
        thread.join()
    if errors:
        raise RuntimeError(
            "Extra High pipeline paused; completed artifacts retained"
        ) from errors[0]
    if len(results) != len(tasks):
        raise RuntimeError(
            f"Extra High pipeline lost task accounting: {len(results)}/{len(tasks)}"
        )
    return results


def collect_tasks(
    domain: str, pilot: bool, spec_id: str | None, seeds: list[int] | None
) -> list[tuple[dict, int]]:
    tasks = []
    for name in ["indoor", "urban"] if domain == "both" else [domain]:
        specs = [
            json.loads(line)
            for line in (ROOT / f"protocol/generation/{name}_specs.jsonl")
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
    return tasks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase", choices=("all", "generate", "build", "render"), default="all"
    )
    parser.add_argument("--domain", choices=("indoor", "urban", "both"), default="both")
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--spec-id")
    parser.add_argument("--seeds", type=int, nargs="+")
    parser.add_argument("--gpus", type=int, nargs="+", default=[0])
    parser.add_argument("--generators", type=int, default=4)
    parser.add_argument("--builders", type=int)
    parser.add_argument(
        "--data-root", type=Path, default=ROOT / "data/gpt6_astra_xhigh_pilot"
    )
    args = parser.parse_args()
    data_root = confined(args.data_root)
    tasks = collect_tasks(args.domain, args.pilot, args.spec_id, args.seeds)
    if not tasks:
        raise ValueError("No matching Extra High tasks")
    guard_path = ROOT / "results/gpt6_astra_xhigh/matrix.lock"
    guard_path.parent.mkdir(parents=True, exist_ok=True)
    with guard_path.open("a") as guard:
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                "A GPT-6 Astra Extra High matrix runner is already active"
            ) from exc
        if args.phase == "all":
            if not 1 <= args.generators <= 4:
                raise ValueError("Generation concurrency must be 1..4")
            builders = args.builders or json.loads(CONFIG.read_text())["build_workers"]
            results = pipeline(tasks, data_root, args.gpus, args.generators, builders)
        else:

            def lane(index: int, gpu: int | None) -> list[dict]:
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
        "method": METHOD,
        "reasoning_effort": "xhigh",
        "data_root": str(data_root),
        "phase": args.phase,
        "runs": len(results),
        "generated": sum(bool(item.get("generation_success")) for item in results),
        "rendered": sum(bool(item.get("render_success")) for item in results),
        "quality_failures": sum(
            item.get("failure_class") == "quality" for item in results
        ),
    }
    suffix = "pilot" if args.pilot else "formal"
    write_json(
        ROOT / f"results/gpt6_astra_xhigh/matrix_{suffix}_{args.phase}.json", report
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
