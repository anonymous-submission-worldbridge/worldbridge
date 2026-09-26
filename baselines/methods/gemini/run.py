#!/usr/bin/env python3
"""Run only the Gemini 3.1 Pro Table-2 generation/build/render matrix."""
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
import shutil
import subprocess
import sys
import time


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
METHOD = "gemini_3_1_pro"
sys.path.insert(0, str((ROOT / "methods")))
from baselines.methods.gemini.adapter import confined
from baselines.methods.gemini.adapter import digest
from baselines.methods.gemini.adapter import generate
from baselines.methods.gemini.adapter import run_process
from baselines.methods.gemini.adapter import utc
from baselines.methods.gemini.adapter import write_json


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
            mean, standard_deviation = float(array.mean()), float(array.std())
            records.append(
                {
                    "path": str(path.relative_to(run)),
                    "mean": mean,
                    "std": standard_deviation,
                }
            )
            if not 0.01 <= mean <= 0.99 or standard_deviation < 0.01:
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
            f"WAIT gpu={gpu} free_mib={free} required_mib={minimum_free_mib}",
            flush=True,
        )
        time.sleep(15)


def compress_attempt_logs(log_directory: Path) -> dict:
    compressed = {}
    for name in ("stdout.log", "stderr.log"):
        path = log_directory / name
        if not path.exists():
            continue
        target = path.with_suffix(path.suffix + ".gz")
        temporary = target.with_suffix(target.suffix + ".tmp")
        original_size = path.stat().st_size
        with path.open("rb") as source, gzip.open(
            temporary, "wb", compresslevel=1
        ) as destination:
            shutil.copyfileobj(source, destination, length=1024 * 1024)
        temporary.replace(target)
        path.unlink()
        compressed[name] = {
            "path": target.name,
            "original_bytes": original_size,
            "compressed_bytes": target.stat().st_size,
            "sha256": digest(target),
        }
    return compressed


def render_run(run: Path, gpu: int | None, build_only: bool = False) -> dict:
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
        ((ROOT / "methods/gemini/protocol/generation/gemini_3_1_pro.json")).read_text()
    )
    (run / "tmp").mkdir(exist_ok=True)
    environment = dict(os.environ)
    for name in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        environment.pop(name, None)
    environment.update(
        CUDA_VISIBLE_DEVICES="" if gpu is None else str(gpu),
        TMPDIR=str(run / "tmp"),
        PYTHONDONTWRITEBYTECODE="1",
        NO_PROXY="*",
        no_proxy="*",
    )
    manifest["execution_isolation"] = {
        "mode": "direct_blender_factory_startup_after_static_ast_validation",
        "amendment": "methods/gemini/protocol/generation/gemini_3_1_pro_pilot_infrastructure_amendment_20260917.json",
        "credentials_and_proxies_removed": True,
    }
    for phase in ["build"] if build_only else ["build", "render"]:
        if phase == "build" and manifest.get("build_success"):
            continue
        attempts = manifest.setdefault(phase + "_attempts", [])
        for index in range(len(attempts) + 1, 4):
            admitted_free = (
                wait_gpu(gpu, int(config["min_render_free_mib"]))
                if phase == "render" and gpu is not None
                else None
            )
            log_directory = run / f"logs/{phase}_{index:02d}"
            log_directory.mkdir(parents=True, exist_ok=False)
            # Unprivileged namespaces are disabled on this host. The frozen
            # pre-scoring pilot amendment therefore uses factory-startup Blender
            # directly after the restrictive generated-code AST validation.
            command = [
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
            limit = int(
                config["build_timeout_s" if phase == "build" else "render_timeout_s"]
            )
            attempt = {
                "index": index,
                "started_at_utc": utc(),
                "gpu": gpu,
                "command": command,
                "timeout_limit_s": limit,
                "gpu_admitted_free_mib": admitted_free,
                "gpu_policy": config["gpu_policy"],
            }
            attempts.append(attempt)
            write_json(manifest_path, manifest)
            stdout_path, stderr_path = (
                log_directory / "stdout.log",
                log_directory / "stderr.log",
            )
            return_code, timed_out = run_process(
                command, run, stdout_path, stderr_path, limit, env=environment
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
                for token in ("out of memory", "cannot allocate memory", "memoryerror")
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
            attempt["log_compression"] = compress_attempt_logs(log_directory)
            if complete:
                manifest[phase + "_success"] = True
                manifest.update(failure_class=None, failure_reason=None)
                write_json(manifest_path, manifest)
                break
            manifest.update(
                failure_class="quality" if quality else "infrastructure",
                failure_reason=f"{phase} failed: {log_directory.relative_to(run)}",
            )
            write_json(manifest_path, manifest)
            if quality:
                return manifest
            if "No CUDA/OPTIX" in logs or (return_code == 11 and not resource_error):
                raise RuntimeError(manifest["failure_reason"] + "\n" + tail)
            if index == 3:
                return manifest
        if not manifest.get(phase + "_success"):
            return manifest
    if build_only:
        return manifest
    validation = validate(run)
    manifest["render_success"] = validation["valid"]
    manifest["ended_at_utc"] = utc()
    manifest["exit_code"] = 0 if validation["valid"] else 2
    if validation["valid"]:
        (run / "SUCCESS").write_text(utc() + "\n")
    else:
        manifest.update(
            failure_class="quality", failure_reason="; ".join(validation["problems"])
        )
    write_json(manifest_path, manifest)
    return manifest


def verify_formal_lock() -> None:
    lock_path = ROOT / "methods/gemini/protocol/generation/gemini_3_1_pro.lock.json"
    if not lock_path.exists():
        raise RuntimeError("Formal Gemini run requires a frozen pilot lock")
    lock = json.loads(lock_path.read_text())
    for relative, expected in lock["files_sha256"].items():
        if digest(ROOT / relative) != expected:
            raise RuntimeError("Frozen source changed: " + relative)


def task(spec: dict, seed: int, data_root: Path, gpu: int | None, phase: str) -> dict:
    config = json.loads(
        ((ROOT / "methods/gemini/protocol/generation/gemini_3_1_pro.json")).read_text()
    )
    if shutil.disk_usage(ROOT).free < int(config["storage"]["minimum_free_bytes"]):
        raise RuntimeError(
            "Less than 50 GiB free; pausing Gemini without deleting artifacts"
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


def select_tasks(
    domain: str, pilot: bool, spec_id: str | None, seeds: list[int] | None
):
    tasks = []
    domains = ["indoor", "urban"] if domain == "both" else [domain]
    for current_domain in domains:
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase", choices=["all", "generate", "build", "render"], default="all"
    )
    parser.add_argument("--domain", choices=["indoor", "urban", "both"], default="both")
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--spec-id")
    parser.add_argument("--seeds", type=int, nargs="+", default=None)
    parser.add_argument("--gpus", type=int, nargs="+", default=[1])
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument(
        "--data-root", type=Path, default=ROOT / "data/gemini_3_1_pro_pilot"
    )
    args = parser.parse_args()
    data_root = confined(args.data_root)
    tasks = select_tasks(args.domain, args.pilot, args.spec_id, args.seeds)
    config = json.loads(
        ((ROOT / "methods/gemini/protocol/generation/gemini_3_1_pro.json")).read_text()
    )
    workers = args.workers or min(
        len(args.gpus), int(config["generation_concurrency_max"])
    )
    if workers < 1 or workers > int(config["generation_concurrency_max"]):
        raise ValueError("Workers exceed frozen Gemini generation concurrency")

    def lane(index: int) -> list[dict]:
        gpu = args.gpus[index % len(args.gpus)]
        return [
            task(spec, seed, data_root, gpu, args.phase)
            for spec, seed in tasks[index::workers]
        ]

    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(lane, index) for index in range(workers)]
        for future in as_completed(futures):
            results.extend(future.result())
    report = {
        "method": METHOD,
        "phase": args.phase,
        "pilot": args.pilot,
        "data_root": str(data_root),
        "expected": len(tasks),
        "completed": len(results),
        "generation_success": sum(
            bool(item.get("generation_success")) for item in results
        ),
        "render_success": sum(bool(item.get("render_success")) for item in results),
        "quality_failures": sum(
            item.get("failure_class") == "quality" for item in results
        ),
        "ended_at_utc": utc(),
    }
    suffix = "pilot" if args.pilot else "formal"
    write_json(
        ROOT / "results/gemini_3_1_pro" / f"matrix_{suffix}_{args.phase}.json", report
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
