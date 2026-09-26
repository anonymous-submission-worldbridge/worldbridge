#!/usr/bin/env python3
"""Run the SpatialGen-only Table-3 surface evaluation matrix.

The expensive SpatialGen generation stage is never invoked.  Each task reads
the successful Table-2 final Gaussian, reconstructs the frozen surface on one
GPU, then runs the shared Recast navigation evaluator on CPU.
"""

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


# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import (
    expand_paths as _wb_expand_paths,
    path_variables as _wb_path_variables,
)

_wb_paths = _wb_path_variables()


import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES_ROOT = REPO_ROOT / "baselines"
PROTOCOL_PATH = (
    BASELINES_ROOT / "methods/spatialgen/protocol/geometry/spatialgen_protocol.json"
)
AGENT_PATH = BASELINES_ROOT / "protocol/geometry/agent.yaml"
RECONSTRUCTOR = (
    BASELINES_ROOT
    / "methods/spatialgen/geometry/tools/reconstruct_spatialgen_surface.py"
)
EVALUATOR = (
    BASELINES_ROOT
    / "methods/spatialgen/geometry/metrics/eval_spatialgen_navigability.py"
)
WORLDUNIT_PYTHON = Path(_wb_expand_paths("${WORLDBRIDGE_PYTHON}"))
NAV_PYTHON = Path(_wb_expand_paths("${WORLDBRIDGE_PYTHON}"))
SPATIAL_SITE = BASELINES_ROOT / "envs/spatialgen/lib/python3.10/site-packages"
REBUILT_RASTERIZER_SITE = BASELINES_ROOT / "work/spatialgen/table3/rebuilt_site"
NAV_SITE = BASELINES_ROOT / "envs/hyworld2/lib/python3.11/site-packages"
if str(REPO_ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(REPO_ROOT))

from baselines.methods.spatialgen.geometry.adapters.spatialgen import locate_artifacts


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_specs() -> list[dict[str, Any]]:
    path = BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def is_current(run_dir: Path) -> bool:
    manifest_path = run_dir / "run_manifest.json"
    metric_path = run_dir / "metrics/navigability.json"
    collision_path = run_dir / "scene/canonical/collision_geometry.npz"
    if not all(
        path.is_file()
        for path in (
            manifest_path,
            metric_path,
            collision_path,
            run_dir / "EVALUATION_SUCCESS",
        )
    ):
        return False
    try:
        manifest = read_json(manifest_path)
        expected = {
            "protocol_sha256": sha256(PROTOCOL_PATH),
            "reconstructor_sha256": sha256(RECONSTRUCTOR),
            "navigation_evaluator_sha256": sha256(EVALUATOR),
            "agent_sha256": sha256(AGENT_PATH),
        }
        if any(manifest.get(key) != value for key, value in expected.items()):
            return False
        if manifest.get("canonical_hashes", {}).get(
            "collision_geometry_sha256"
        ) != sha256(collision_path):
            return False
        if manifest.get("metric_hashes", {}).get("navigability_sha256") != sha256(
            metric_path
        ):
            return False
        return True
    except Exception:
        return False


def command_record(
    command: list[str], log_path: Path, env: dict[str, str], timeout_s: int
) -> dict[str, Any]:
    started = utc_now()
    before = time.monotonic()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        log.write("COMMAND " + json.dumps(command) + "\n")
        log.flush()
        try:
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout_s,
                check=False,
            )
            exit_code = int(completed.returncode)
            timed_out = False
        except subprocess.TimeoutExpired:
            exit_code = 124
            timed_out = True
    return {
        "command": command,
        "log": str(log_path.relative_to(BASELINES_ROOT)),
        "started_at_utc": started,
        "ended_at_utc": utc_now(),
        "wall_time_s": time.monotonic() - before,
        "exit_code": exit_code,
        "timed_out": timed_out,
    }


def stage_source_run(
    source_run: Path, stage_root: Path, spec_id: str, seed: int
) -> tuple[Path, dict[str, Any]]:
    before = time.monotonic()
    artifacts = locate_artifacts(source_run)
    staged_run = stage_root / spec_id / f"seed_{seed}"
    copied = 0
    copied_bytes = 0
    for source in artifacts.values():
        relative = source.relative_to(source_run)
        target = staged_run / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file() and target.stat().st_size == source.stat().st_size:
            continue
        temporary = target.with_suffix(target.suffix + ".copying")
        shutil.copy2(source, temporary)
        temporary.replace(target)
        copied += 1
        copied_bytes += source.stat().st_size
    return staged_run, {
        "cache_root": str(stage_root),
        "staged_run": str(staged_run),
        "copied_files": copied,
        "copied_bytes": copied_bytes,
        "wall_time_s": time.monotonic() - before,
    }


def run_task(
    spec_id: str,
    seed: int,
    gpu: int,
    source_root: Path,
    output_root: Path,
    log_root: Path,
    force: bool,
    maximum_attempts: int,
    stage_root: Path,
) -> dict[str, Any]:
    source_run = source_root / spec_id / f"seed_{seed}"
    output_run = output_root / spec_id / f"seed_{seed}"
    output_run.mkdir(parents=True, exist_ok=True)
    row: dict[str, Any] = {
        "spec_id": spec_id,
        "seed": seed,
        "gpu": gpu,
        "source_run": str(source_run),
        "output_run": str(output_run),
    }
    if not force and is_current(output_run):
        row.update(status="resumed_current", ended_at_utc=utc_now())
        return row
    try:
        staged_run, staging = stage_source_run(source_run, stage_root, spec_id, seed)
        row["staging"] = staging
    except Exception as error:
        staged_run = source_run
        row["staging"] = {
            "error": f"{type(error).__name__}: {error}",
            "fallback": str(source_run),
        }

    common_env = os.environ.copy()
    common_env.update(
        {
            "CUDA_VISIBLE_DEVICES": str(gpu),
            "TMPDIR": str(BASELINES_ROOT / "work/spatialgen/table3/tmp"),
            "TORCH_EXTENSIONS_DIR": str(
                BASELINES_ROOT / "work/spatialgen/table3/torch_extensions"
            ),
            "MPLCONFIGDIR": str(BASELINES_ROOT / "work/spatialgen/table3/matplotlib"),
            "PYTHONPATH": os.pathsep.join(
                (str(REBUILT_RASTERIZER_SITE), str(SPATIAL_SITE))
            ),
        }
    )
    reconstruction_attempts = []
    for attempt in range(1, maximum_attempts + 1):
        reconstruction = command_record(
            [
                str(WORLDUNIT_PYTHON),
                str(RECONSTRUCTOR),
                "--source-run",
                str(staged_run),
                "--output-run",
                str(output_run),
                "--provenance-source-run",
                str(source_run),
                "--protocol",
                str(PROTOCOL_PATH),
            ],
            log_root / f"{spec_id}_seed_{seed}_reconstruct_attempt_{attempt:02d}.log",
            common_env,
            timeout_s=20 * 60,
        )
        reconstruction_attempts.append(reconstruction)
        if reconstruction["exit_code"] == 0:
            break
    row["reconstruction_attempts"] = reconstruction_attempts

    nav_env = os.environ.copy()
    nav_env["PYTHONPATH"] = os.pathsep.join((str(NAV_SITE), str(REPO_ROOT)))
    evaluation_attempts = []
    for attempt in range(1, maximum_attempts + 1):
        evaluation = command_record(
            [
                str(NAV_PYTHON),
                str(EVALUATOR),
                "--run-dir",
                str(output_run),
                "--agent",
                str(AGENT_PATH),
            ],
            log_root / f"{spec_id}_seed_{seed}_evaluate_attempt_{attempt:02d}.log",
            nav_env,
            timeout_s=5 * 60,
        )
        evaluation_attempts.append(evaluation)
        if evaluation["exit_code"] == 0:
            break
    row["evaluation_attempts"] = evaluation_attempts
    metric_path = output_run / "metrics/navigability.json"
    if metric_path.is_file():
        metric = read_json(metric_path)
        row["metrics"] = {
            key: metric.get(key)
            for key in (
                "navigable_area_ratio",
                "connected_area_ratio",
                "navmesh_success",
            )
        }
    row["status"] = (
        "complete"
        if evaluation_attempts[-1]["exit_code"] == 0 and metric_path.is_file()
        else "runner_failure"
    )
    row["ended_at_utc"] = utc_now()
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("pilot", "formal"), required=True)
    parser.add_argument(
        "--gpus", default="0", help="Comma-separated physical GPU indices"
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--maximum-attempts", type=int, default=3)
    parser.add_argument(
        "--stage-root",
        type=Path,
        default=Path("/tmp/worldbridge_spatialgen_table3_cache"),
        help="Transient local cache for the immutable Table-2 files",
    )
    parser.add_argument(
        "--only",
        action="append",
        help="Optional SPEC_ID:SEED selector; repeat as needed",
    )
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()

    protocol = read_json(PROTOCOL_PATH)
    specs = load_specs()
    if args.phase == "pilot":
        specs = [spec for spec in specs if spec["spec_id"].endswith("_00")]
        seeds = [0, 1]
        source_root = args.source_root or BASELINES_ROOT / protocol["reuse"][
            "pilot_cache"
        ].removeprefix("baselines/")
        output_root = (
            args.output_root or BASELINES_ROOT / "data/table3_pilot/indoor/spatialgen"
        )
    else:
        seeds = [int(value) for value in protocol["seeds"]]
        source_root = (
            args.source_root or BASELINES_ROOT / "data/table2/indoor/spatialgen"
        )
        output_root = (
            args.output_root or BASELINES_ROOT / "data/table3/indoor/spatialgen"
        )
    tasks = [(spec["spec_id"], seed) for spec in specs for seed in seeds]
    if args.only:
        selected = set()
        for value in args.only:
            spec_id, seed_text = value.rsplit(":", 1)
            selected.add((spec_id, int(seed_text)))
        tasks = [task for task in tasks if task in selected]
    gpus = [int(value) for value in args.gpus.split(",") if value.strip()]
    if not gpus:
        raise ValueError("At least one GPU is required")
    if args.maximum_attempts < 1:
        raise ValueError("--maximum-attempts must be positive")
    args.stage_root.mkdir(parents=True, exist_ok=True)
    for path in (
        output_root,
        BASELINES_ROOT / "work/spatialgen/table3/tmp",
        BASELINES_ROOT / "work/spatialgen/table3/torch_extensions",
        BASELINES_ROOT / "work/spatialgen/table3/matplotlib",
    ):
        path.mkdir(parents=True, exist_ok=True)
    log_root = BASELINES_ROOT / f"evaluation/geometry/logs/spatialgen/{args.phase}"
    log_root.mkdir(parents=True, exist_ok=True)

    assignments = [tasks[index :: len(gpus)] for index in range(len(gpus))]
    rows: list[dict[str, Any]] = []
    lock = threading.Lock()

    def worker(gpu: int, assigned: list[tuple[str, int]]) -> None:
        for spec_id, seed in assigned:
            row = run_task(
                spec_id,
                seed,
                gpu,
                source_root,
                output_root,
                log_root,
                args.force,
                args.maximum_attempts,
                args.stage_root,
            )
            with lock:
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(gpus)) as pool:
        futures = [
            pool.submit(worker, gpu, assigned)
            for gpu, assigned in zip(gpus, assignments)
        ]
        for future in futures:
            future.result()
    rows.sort(key=lambda row: (row["spec_id"], row["seed"]))
    summary_path = (
        BASELINES_ROOT
        / f"evaluation/geometry/results/spatialgen_{args.phase}_matrix.json"
    )
    atomic_json(
        summary_path,
        {
            "method": "spatialgen",
            "phase": args.phase,
            "started_tasks": len(tasks),
            "source_root": str(source_root),
            "output_root": str(output_root),
            "gpus": gpus,
            "complete": sum(
                row["status"] in ("complete", "resumed_current") for row in rows
            ),
            "rows": rows,
        },
    )
    failures = [
        row for row in rows if row["status"] not in ("complete", "resumed_current")
    ]
    print(
        json.dumps(
            {
                "tasks": len(rows),
                "runner_failures": len(failures),
                "summary": str(summary_path),
            }
        )
    )
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
