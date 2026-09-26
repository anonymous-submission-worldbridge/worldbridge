#!/usr/bin/env python3
"""Resume the frozen formal matrix with disclosed accelerated local storage."""
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


import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(ROOT))
import baselines.methods.gpt.run_xhigh_matrix as matrix

AMENDMENT = (
    ROOT
    / "methods/gpt/protocol/generation/gpt6_astra_xhigh_12h_capacity_amendment_20260913.json"
)
DATA_ROOT = Path(
    _wb_expand_paths("${WORLDBRIDGE_CACHE}/worldbridge_gpt6_astra_xhigh_uid2002/table2")
)
SANDBOX_RUN = ROOT / "tmp/gpt6_astra_xhigh_sandbox_mount"
FROZEN_RUN_PROCESS = matrix.run_process


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def operational_confined(path: Path) -> Path:
    resolved = Path(path).resolve()
    allowed = DATA_ROOT.resolve()
    if not (resolved == allowed or resolved.is_relative_to(allowed)):
        raise ValueError(
            "Accelerated formal output must remain under the disclosed /tmp storage root"
        )
    return resolved


def operational_run_process(
    cmd, work, stdout_path, stderr_path, timeout, env=None, stdin=None
):
    """Map only a /tmp formal run into the otherwise frozen Blender sandbox."""
    if cmd and cmd[0] == "bwrap":
        run = str(Path(work).resolve())
        if not Path(run).is_relative_to(DATA_ROOT.resolve()):
            raise RuntimeError(
                "Unexpected Blender work path outside disclosed formal storage"
            )
        binding = next(
            (
                index
                for index in range(len(cmd) - 2)
                if cmd[index : index + 3] == ["--bind", run, run]
            ),
            None,
        )
        if binding is None:
            raise RuntimeError("Frozen Blender command lacks the expected run bind")
        del cmd[binding : binding + 3]
        sandbox = str(SANDBOX_RUN)
        for index, argument in enumerate(cmd):
            if argument == run or argument.startswith(run + "/"):
                cmd[index] = sandbox + argument[len(run) :]
        cmd[binding:binding] = ["--bind", run, sandbox]
        if env is None:
            raise RuntimeError("Frozen Blender command lacks its environment")
        env["TMPDIR"] = str(SANDBOX_RUN / "tmp")
    return FROZEN_RUN_PROCESS(
        cmd, work, stdout_path, stderr_path, timeout, env=env, stdin=stdin
    )


def operational_task(
    spec: dict, seed: int, data_root: Path, gpu: int | None, phase: str
) -> dict:
    config = json.loads(matrix.CONFIG.read_text())
    amendment = json.loads(AMENDMENT.read_text())
    effective_stop = amendment["storage_safety"]["effective_disk_stop_free_gib"]
    if shutil.disk_usage(data_root).free < effective_stop * 1024**3:
        raise RuntimeError(
            "Extra High effective disk safety threshold reached; no new task started"
        )
    matrix.verify_formal_lock()
    run = data_root / spec["domain"] / matrix.METHOD / spec["spec_id"] / f"seed_{seed}"
    print(
        f"XHIGH_START {spec['spec_id']} seed={seed} phase={phase} gpu={gpu}", flush=True
    )
    manifest = (
        matrix.generate(spec, seed, data_root)
        if phase in {"all", "generate"}
        else json.loads((run / "run_manifest.json").read_text())
    )
    if phase in {"all", "build", "render"}:
        manifest = matrix.render_run(run, gpu, build_only=phase == "build")
    print(
        f"XHIGH_DONE {spec['spec_id']} seed={seed} generated={manifest.get('generation_success')} "
        f"rendered={manifest.get('render_success')} failure={manifest.get('failure_class')}",
        flush=True,
    )
    return manifest


def main() -> int:
    matrix.verify_formal_lock()
    lock = json.loads(matrix.LOCK.read_text())
    amendment = json.loads(AMENDMENT.read_text())
    scientific = amendment["unchanged_scientific_configuration"]
    if (
        amendment.get("method") != matrix.METHOD
        or scientific.get("model") != lock.get("model")
        or scientific.get("reasoning_effort") != lock.get("reasoning_effort")
        or scientific.get("codex_version") != lock.get("codex_version")
        or scientific.get("effective_generation_timeout_s")
        != lock.get("effective_generation_timeout_s")
    ):
        raise RuntimeError("Capacity amendment does not preserve the formal lock")
    capacity = amendment["execution_capacity"]
    expected_capacity = {
        "generation_workers_before": 2,
        "generation_workers_after": 16,
        "build_workers": 16,
        "render_gpus": [0, 1, 2, 5],
        "gpu_policy": "remaining_memory_sharing",
        "minimum_render_free_mib": 8192,
    }
    config = json.loads(matrix.CONFIG.read_text())
    storage = amendment["storage_safety"]
    if (
        capacity != expected_capacity
        or capacity["minimum_render_free_mib"] != config["min_render_free_mib"]
        or storage["registered_disk_stop_free_gib"] != config["disk_stop_free_gib"]
        or storage["effective_disk_stop_free_gib"] != 10
        or Path(storage["formal_storage_root"]) != DATA_ROOT
        or storage["render_sandbox_mount"] != str(SANDBOX_RUN)
    ):
        raise RuntimeError("Unexpected operational capacity, storage, or GPU guard")
    SANDBOX_RUN.mkdir(parents=True, exist_ok=True)
    if SANDBOX_RUN.is_symlink() or any(SANDBOX_RUN.iterdir()):
        raise RuntimeError(
            "Blender sandbox mount point must be an empty real directory"
        )
    tasks = matrix.collect_tasks("both", False, None, None)
    if len(tasks) != 200:
        raise RuntimeError("Frozen formal matrix is not 200 slots")
    guard_path = ROOT / "results/gpt6_astra_xhigh/matrix.lock"
    guard_path.parent.mkdir(parents=True, exist_ok=True)
    with guard_path.open("a") as guard:
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                "A GPT-6 Astra Extra High matrix runner is already active"
            ) from exc
        matrix.generate.__globals__["confined"] = operational_confined
        matrix.run_process = operational_run_process
        matrix.task = operational_task
        results = matrix.pipeline(
            tasks,
            DATA_ROOT,
            capacity["render_gpus"],
            capacity["generation_workers_after"],
            capacity["build_workers"],
        )
    report = {
        "finished_at_utc": matrix.utc(),
        "method": matrix.METHOD,
        "reasoning_effort": "xhigh",
        "data_root": str(DATA_ROOT),
        "phase": "all",
        "runs": len(results),
        "generated": sum(bool(item.get("generation_success")) for item in results),
        "rendered": sum(bool(item.get("render_success")) for item in results),
        "quality_failures": sum(
            item.get("failure_class") == "quality" for item in results
        ),
        "capacity_amendment": str(AMENDMENT.relative_to(ROOT)),
        "capacity_amendment_sha256": digest(AMENDMENT),
        "formal_lock_sha256": digest(matrix.LOCK),
    }
    matrix.write_json(
        ROOT / "results/gpt6_astra_xhigh/matrix_formal_all_accelerated.json", report
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
