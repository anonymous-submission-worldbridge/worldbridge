#!/usr/bin/env python3
"""Run the SynCity 3000 pilot or formal Table-2 matrix on selected GPUs."""

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
import concurrent.futures
import json
import os
import queue
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
REPO_ROOT = BASELINES_ROOT.parent
PYTHON = BASELINES_ROOT / "envs/syncity-3k/bin/python"
ADAPTER = BASELINES_ROOT / "methods/syncity/adapter.py"
RENDERER = BASELINES_ROOT / "methods/syncity/tools/render_syncity_generation.py"
SPEC_FILES = {
    "indoor": (BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"),
    "urban": (BASELINES_ROOT / "protocol/generation/urban_specs.jsonl"),
}
GENERATION_METHOD_FAILURE_PATTERNS = {
    "empty_sparse_latent": (
        "Expected reduction dim to be specified for input.numel() == 0"
    ),
}
MIN_REPRODUCED_METHOD_FAILURES = 3


def load_specs(domain: str) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in SPEC_FILES[domain].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def select_specs(domain: str, phase: str) -> list[dict[str, Any]]:
    specs = load_specs(domain)
    if phase == "formal":
        return specs
    first_by_category: dict[str, dict[str, Any]] = {}
    for spec in specs:
        first_by_category.setdefault(str(spec["category"]), spec)
    return list(first_by_category.values())


def run_dir(data_root: Path, task: dict[str, Any]) -> Path:
    return (
        data_root
        / task["domain"]
        / "syncity3k"
        / task["spec_id"]
        / f"seed_{task['seed']}"
    )


def gpu_state(gpu: int) -> dict[str, int] | None:
    completed = subprocess.run(
        [
            "nvidia-smi",
            f"--id={gpu}",
            "--query-gpu=memory.free,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        return None
    free, utilization = completed.stdout.strip().split(",")
    return {"free_mib": int(free.strip()), "utilization": int(utilization.strip())}


def wait_for_gpu(
    gpu: int,
    minimum_free_mib: int,
    maximum_utilization: int,
    stop_when_empty: queue.Queue[dict[str, Any]] | None = None,
) -> bool:
    while True:
        if stop_when_empty is not None and stop_when_empty.empty():
            return False
        state = gpu_state(gpu)
        if (
            state is not None
            and state["free_mib"] >= minimum_free_mib
            and state["utilization"] <= maximum_utilization
        ):
            return True
        description = "unavailable" if state is None else str(state)
        print(f"SYNCITY3K_WAIT gpu={gpu} state={description}", flush=True)
        time.sleep(30)


def environment_for_gpu(gpu: int) -> dict[str, str]:
    environment = dict(os.environ)
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        environment.pop(name, None)
    cuda_home = "/usr/local/cuda-12.4"
    if not Path(cuda_home).exists():
        cuda_home = "/usr/local/cuda"
    shim_root = BASELINES_ROOT / "methods/syncity/runtime/syncity3k"
    source_root = BASELINES_ROOT / "vendor/syncity-3k"
    cuda_runtime = "/usr/local/cuda-12.1/targets/x86_64-linux/lib"
    library_path = os.pathsep.join(
        part for part in (cuda_runtime, environment.get("LD_LIBRARY_PATH", "")) if part
    )
    python_path = os.pathsep.join(
        part
        for part in (
            str(shim_root),
            str(source_root),
            environment.get("PYTHONPATH", ""),
        )
        if part
    )
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": str(gpu),
            "HF_HOME": str(BASELINES_ROOT / "checkpoints/syncity3k/huggingface"),
            "HF_HUB_CACHE": str(
                BASELINES_ROOT / "checkpoints/syncity3k/huggingface/hub"
            ),
            "TORCH_HOME": str(BASELINES_ROOT / "checkpoints/syncity3k/torch"),
            "XDG_CACHE_HOME": str(BASELINES_ROOT / "cache/syncity3k/xdg"),
            "TORCH_EXTENSIONS_DIR": str(
                BASELINES_ROOT / "cache/syncity3k/torch_extensions"
            ),
            "WARP_CACHE_PATH": str(BASELINES_ROOT / "cache/syncity3k/warp"),
            "TMPDIR": str(BASELINES_ROOT / "tmp/syncity3k"),
            "CUDA_HOME": cuda_home,
            "PATH": f"{PYTHON.parent}:{cuda_home}/bin:{environment.get('PATH', '')}",
            "MAX_JOBS": "8",
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": python_path,
            "LD_LIBRARY_PATH": library_path,
            "TOKENIZERS_PARALLELISM": "false",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "DIFFUSERS_OFFLINE": "1",
            "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
            "ATTN_BACKEND": "xformers",
            "SPARSE_ATTN_BACKEND": "xformers",
        }
    )
    return environment


def run_command(command: list[str], environment: dict[str, str]) -> tuple[int, str]:
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    print(
        completed.stdout,
        end="" if completed.stdout.endswith("\n") else "\n",
        flush=True,
    )
    return completed.returncode, completed.stdout


def generation_method_failure_code(detail: str) -> str | None:
    for code, pattern in GENERATION_METHOD_FAILURE_PATTERNS.items():
        if pattern in detail:
            return code
    return None


def reproduced_generation_method_failure(target: Path) -> tuple[str, str] | None:
    manifest_path = target / "run_manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    failures: list[tuple[str, str]] = []
    for attempt in manifest.get("attempts", []):
        if attempt.get("phase") != "generation" or attempt.get("success") is not False:
            continue
        detail = str(attempt.get("detail", ""))
        code = generation_method_failure_code(detail)
        if code is not None:
            failures.append((code, detail))
    if len(failures) < MIN_REPRODUCED_METHOD_FAILURES:
        return None
    recent = failures[-MIN_REPRODUCED_METHOD_FAILURES:]
    if len({code for code, _ in recent}) != 1:
        return None
    return recent[-1]


def terminalize_generation_method_failure(
    target: Path, failure_code: str, detail: str
) -> None:
    manifest_path = target / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "generation_success": False,
            "render_success": False,
            "failure_reason": "generation_method_failure",
            "failure_code": failure_code,
            "failure_detail": detail[-6000:],
            "terminal_failure_phase": "generation",
            "reproduced_failure_count_required": MIN_REPRODUCED_METHOD_FAILURES,
        }
    )
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(manifest_path)
    (target / "SUCCESS").unlink(missing_ok=True)
    (target / "GENERATION_SUCCESS").unlink(missing_ok=True)
    (target / "QUALITY_FAILURE").write_text(
        f"syncity3k generation method failure: {failure_code}\n",
        encoding="utf-8",
    )


def run_task(
    gpu: int,
    task: dict[str, Any],
    data_root: Path,
    force: bool,
    retries: int,
    minimum_free_mib: int,
) -> dict[str, Any]:
    target = run_dir(data_root, task)
    if (target / "SUCCESS").exists() and not force:
        return {**task, "gpu": gpu, "status": "skipped_success"}
    if (target / "QUALITY_FAILURE").exists() and not force:
        return {**task, "gpu": gpu, "status": "skipped_quality_failure"}
    if not force:
        reproduced = reproduced_generation_method_failure(target)
        if reproduced is not None:
            failure_code, failure_detail = reproduced
            terminalize_generation_method_failure(target, failure_code, failure_detail)
            return {
                **task,
                "gpu": gpu,
                "status": "quality_failure",
                "detail": (
                    "deterministic generation method failure reproduced at least "
                    f"{MIN_REPRODUCED_METHOD_FAILURES} times: {failure_code}"
                ),
            }
    environment = environment_for_gpu(gpu)
    generation_command = [
        str(PYTHON),
        str(ADAPTER),
        "run",
        "--domain",
        task["domain"],
        "--spec-id",
        task["spec_id"],
        "--seed",
        str(task["seed"]),
        "--data-root",
        str(data_root),
    ]
    if force:
        generation_command.append("--force")
    last_output = ""
    for attempt in range(retries + 1):
        # The task is already reserved by this worker.  Keep waiting for this
        # GPU if another process races us after the pre-claim availability
        # check; the shared queue may legitimately be empty for the last task.
        wait_for_gpu(gpu, minimum_free_mib, 10)
        code, last_output = run_command(generation_command, environment)
        if code == 0:
            break
        if attempt < retries:
            print(
                f"SYNCITY3K_RETRY phase=generation gpu={gpu} task={task} "
                f"attempt={attempt + 2}",
                flush=True,
            )
    else:
        failure_code = generation_method_failure_code(last_output)
        reproduced = reproduced_generation_method_failure(target)
        if reproduced is not None and failure_code == reproduced[0]:
            terminalize_generation_method_failure(target, failure_code, reproduced[1])
            return {
                **task,
                "gpu": gpu,
                "status": "quality_failure",
                "detail": (
                    "deterministic generation method failure reproduced at least "
                    f"{MIN_REPRODUCED_METHOD_FAILURES} times: {failure_code}"
                ),
            }
        return {
            **task,
            "gpu": gpu,
            "status": "generation_failed",
            "detail": last_output[-4000:],
        }
    render_command = [str(PYTHON), str(RENDERER), "--run-dir", str(target)]
    if force:
        render_command.append("--force")
    wait_for_gpu(gpu, minimum_free_mib, 10)
    code, last_output = run_command(render_command, environment)
    if code == 0:
        status = "success"
    else:
        manifest_path = target / "run_manifest.json"
        manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest_path.is_file()
            else {}
        )
        status = (
            "quality_failure"
            if manifest.get("failure_reason") == "render_validator_failure"
            else "render_failed"
        )
    return {**task, "gpu": gpu, "status": status, "detail": last_output[-4000:]}


def worker(
    gpu: int,
    task_queue: queue.Queue[dict[str, Any]],
    data_root: Path,
    force: bool,
    retries: int,
    minimum_free_mib: int,
    minimum_free_gib: float,
) -> list[dict[str, Any]]:
    results = []
    while not task_queue.empty():
        free_gib = shutil.disk_usage(BASELINES_ROOT).free / (1024**3)
        if free_gib < minimum_free_gib:
            results.append(
                {
                    "gpu": gpu,
                    "status": "low_disk",
                    "free_gib": free_gib,
                }
            )
            break
        # Do not reserve a task for a busy GPU.  Any worker that reaches the
        # frozen availability threshold may take the next task, so long-lived
        # jobs on one card cannot strand a static shard while other cards idle.
        if not wait_for_gpu(gpu, minimum_free_mib, 10, stop_when_empty=task_queue):
            break
        try:
            task = task_queue.get_nowait()
        except queue.Empty:
            break
        result = run_task(gpu, task, data_root, force, retries, minimum_free_mib)
        results.append(result)
        task_queue.task_done()
        print(f"SYNCITY3K_TASK_END {json.dumps(result, sort_keys=True)}", flush=True)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("pilot", "formal"), required=True)
    parser.add_argument(
        "--domains", nargs="+", choices=tuple(SPEC_FILES), default=list(SPEC_FILES)
    )
    parser.add_argument("--gpus", nargs="+", type=int, default=[1])
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-infra-retries", type=int, default=2)
    parser.add_argument("--minimum-free-mib", type=int, default=44000)
    parser.add_argument("--minimum-free-gib", type=float, default=100.0)
    parser.add_argument("--spec-id", action="append", default=[])
    parser.add_argument("--seed", action="append", type=int, default=[])
    args = parser.parse_args()
    if len(set(args.gpus)) != len(args.gpus):
        raise ValueError("GPU IDs must be unique")
    default_root = (
        BASELINES_ROOT / "data/table2_syncity3k_pilot"
        if args.phase == "pilot"
        else BASELINES_ROOT / "data/table2"
    )
    data_root = (args.data_root or default_root).resolve()
    try:
        data_root.relative_to(BASELINES_ROOT.resolve())
    except ValueError as exc:
        raise ValueError("data-root must remain below baselines/") from exc
    selected_ids = set(args.spec_id)
    selected_seeds = set(args.seed)
    expected_seeds = (0, 1) if args.phase == "pilot" else (0, 1, 2, 3)
    if selected_seeds and not selected_seeds.issubset({0, 1, 2, 3}):
        raise ValueError("Seeds must be in 0,1,2,3")
    tasks = []
    for domain in args.domains:
        for spec in select_specs(domain, args.phase):
            if selected_ids and spec["spec_id"] not in selected_ids:
                continue
            for seed in expected_seeds:
                if selected_seeds and seed not in selected_seeds:
                    continue
                tasks.append(
                    {"domain": domain, "spec_id": spec["spec_id"], "seed": seed}
                )
    if selected_ids - {task["spec_id"] for task in tasks}:
        raise ValueError(
            f"Requested spec IDs not selected: {sorted(selected_ids - {task['spec_id'] for task in tasks})}"
        )
    all_results: list[dict[str, Any]] = []
    pending: queue.Queue[dict[str, Any]] = queue.Queue()
    for task in tasks:
        target = run_dir(data_root, task)
        terminal_marker = next(
            (
                (marker, status)
                for marker, status in (
                    ("SUCCESS", "skipped_success"),
                    ("QUALITY_FAILURE", "skipped_quality_failure"),
                )
                if (target / marker).exists()
            ),
            None,
        )
        if terminal_marker is not None and not args.force:
            result = {**task, "gpu": None, "status": terminal_marker[1]}
            all_results.append(result)
            print(
                f"SYNCITY3K_TASK_END {json.dumps(result, sort_keys=True)}",
                flush=True,
            )
        else:
            pending.put(task)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(args.gpus)) as executor:
        futures = [
            executor.submit(
                worker,
                gpu,
                pending,
                data_root,
                args.force,
                args.max_infra_retries,
                args.minimum_free_mib,
                args.minimum_free_gib,
            )
            for gpu in args.gpus
        ]
        for future in concurrent.futures.as_completed(futures):
            all_results.extend(future.result())
    result_path = BASELINES_ROOT / "results/syncity3k" / f"matrix_{args.phase}.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(
            {
                "phase": args.phase,
                "data_root": str(data_root),
                "gpus": args.gpus,
                "tasks": all_results,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    terminal_statuses = {
        "success",
        "skipped_success",
        "quality_failure",
        "skipped_quality_failure",
    }
    failures = sum(row["status"] not in terminal_statuses for row in all_results)
    print(
        f"SYNCITY3K_MATRIX_COMPLETE phase={args.phase} tasks={len(all_results)} "
        f"failures={failures} output={result_path}",
        flush=True,
    )
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
