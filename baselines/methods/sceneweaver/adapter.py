#!/usr/bin/env python3
"""Frozen SceneWeaver adapter for the Table-2 indoor protocol.

The upstream project is kept below ``baselines/vendor`` and all mutable state,
including caches and generated scenes, stays below ``baselines``.  The only
external reads are the preinstalled planner environment, the user-provided API
key, Blender, and the public 3D-FUTURE asset pack.
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
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES_ROOT = REPO_ROOT / "baselines"
SCENEWEAVER_ROOT = BASELINES_ROOT / "vendor/SceneWeaver"
PIPELINE_ROOT = SCENEWEAVER_ROOT / "Pipeline"
PLANNER_PYTHON = Path(_wb_expand_paths("${WORLDBRIDGE_PYTHON}"))
EXECUTOR_PYTHON = BASELINES_ROOT / "envs/sceneweaver_executor/bin/python"
BLENDER_BIN = Path(_wb_expand_paths("${BLENDER_BIN}"))
API_KEY_FILE = Path(
    _wb_expand_paths("${WORLDBRIDGE_EXTERNAL}/SceneWeaver/Pipeline/key.txt")
)
ASSET_INDEX = BASELINES_ROOT / "cache/sceneweaver/3d_future_index.json"
BLENDER_RENDER_SCRIPT = (
    BASELINES_ROOT / "methods/sceneweaver/tools/blender_render_sceneweaver.py"
)
DEFAULT_SPEC_FILE = BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"
DEFAULT_DATA_ROOT = BASELINES_ROOT / "data/table2"
PROTOCOL_FILE = BASELINES_ROOT / "protocol/generation/protocol.yaml"

UPSTREAM_COMMIT = "7ae54b2ec3fc66147704faa7daf7b017ba8b1bd9"
LLM_API_TYPE = "openrouter"
LLM_BASE_URL = "https://openrouter.ai/api/v1"
LLM_MODEL = "minimax/minimax-m3:free"
LLM_TEMPERATURE = 0.3
LLM_MAX_TOKENS = 8096
LLM_RETRY_ATTEMPTS = 6
LLM_RETRY_MIN_DELAY_S = 2
LLM_RETRY_MAX_DELAY_S = 60
PLANNER_MAX_ATTEMPTS = 15
PREVIEW_RESOLUTION = (1024, 576)
PREVIEW_SAMPLES = 64
CAMERA_HEIGHT_METERS = 1.55
PATCHED_SOURCE_FILES = (
    "Pipeline/main.py",
    "Pipeline/TongGPT.py",
    "Pipeline/app/config.py",
    "Pipeline/app/llm.py",
    "Pipeline/app/llm_audit.py",
    "Pipeline/app/agent/scenedesigner.py",
    "Pipeline/app/tool/add_crowd.py",
    "Pipeline/app/tool/add_gpt.py",
    "Pipeline/app/tool/init_gpt.py",
    "Pipeline/app/tool/update_infinigen.py",
    "infinigen/assets/materials/common.py",
    "infinigen/core/constraints/example_solver/solve.py",
    "infinigen/core/constraints/example_solver/moves/addition.py",
    "infinigen/assets/objaverse_assets/local_retrieve.py",
    "infinigen/assets/objaverse_assets/objaverse_category.py",
    "infinigen_examples/steps/tools.py",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def assert_below_baselines(path: Path) -> None:
    resolved = path.resolve()
    try:
        resolved.relative_to(BASELINES_ROOT.resolve())
    except ValueError as error:
        raise ValueError(
            f"Mutable SceneWeaver output must stay below {BASELINES_ROOT}: {path}"
        ) from error


def load_specs(path: Path) -> dict[str, dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            spec = json.loads(line)
            spec_id = spec["spec_id"]
            if spec_id in specs:
                raise ValueError(f"Duplicate spec_id={spec_id!r} at line {line_number}")
            specs[spec_id] = spec
    return specs


def method_seed(spec: dict[str, Any], logical_seed: int) -> int:
    if logical_seed not in (0, 1, 2, 3):
        raise ValueError("Table-2 logical seed must be one of 0,1,2,3")
    return int(spec["spec_index"]) * 4 + logical_seed


def source_hashes() -> dict[str, str]:
    return {path: sha256_file(SCENEWEAVER_ROOT / path) for path in PATCHED_SOURCE_FILES}


def build_native_input(spec: dict[str, Any], logical_seed: int) -> dict[str, Any]:
    return {
        "adapter": "sceneweaver",
        "spec_id": spec["spec_id"],
        "logical_seed": logical_seed,
        "method_seed": method_seed(spec, logical_seed),
        "prompt": spec["prompt_en"],
        "compiled_fields": ["prompt_en"],
        "unsupported_native_fields": ["extent_m", "required_facts", "layout_rubric"],
        "initializer": "init_gpt",
        "planner": {
            "api_type": LLM_API_TYPE,
            "base_url": LLM_BASE_URL,
            "model": LLM_MODEL,
            "temperature": LLM_TEMPERATURE,
            "max_tokens": LLM_MAX_TOKENS,
            "max_attempts": PLANNER_MAX_ATTEMPTS,
            "transport_retry": {
                "attempts": LLM_RETRY_ATTEMPTS,
                "min_delay_s": LLM_RETRY_MIN_DELAY_S,
                "max_delay_s": LLM_RETRY_MAX_DELAY_S,
                "backoff": "exponential_without_jitter",
            },
            "seed_supported": False,
        },
        "initial_tools": ["init_gpt"],
        "refinement_tools": [
            "add_gpt",
            "add_crowd",
            "add_relation",
            "update_layout",
            "update_rotation",
            "update_size",
            "terminate",
            "remove_object",
        ],
        "assets": {
            "retrieval": "deterministic_3d_future_metadata_fallback",
            "index": str(ASSET_INDEX),
            "index_sha256": sha256_file(ASSET_INDEX),
        },
    }


def baseline_environment(gpu: int) -> dict[str, str]:
    cache = BASELINES_ROOT / "cache/sceneweaver"
    for path in (
        cache / "pycache",
        cache / "xdg",
        cache / "config",
        cache / "huggingface",
        cache / "torch",
        cache / "tiktoken",
        cache / "matplotlib",
        cache / "tmp",
    ):
        path.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "CUDA_VISIBLE_DEVICES": str(gpu),
            "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": str(cache / "pycache"),
            "MPLCONFIGDIR": str(cache / "matplotlib"),
            "XDG_CACHE_HOME": str(cache / "xdg"),
            "XDG_CONFIG_HOME": str(cache / "config"),
            "HF_HOME": str(cache / "huggingface"),
            "TORCH_HOME": str(cache / "torch"),
            "TIKTOKEN_CACHE_DIR": str(cache / "tiktoken"),
            "TMPDIR": str(cache / "tmp"),
            "SCENEWEAVER_EXECUTOR_PYTHON": str(EXECUTOR_PYTHON),
            "SCENEWEAVER_3D_FUTURE_INDEX": str(ASSET_INDEX),
            "SCENEWEAVER_LLM_API_KEY_FILE": str(API_KEY_FILE),
            "SCENEWEAVER_LLM_API_TYPE": LLM_API_TYPE,
            "SCENEWEAVER_LLM_BASE_URL": LLM_BASE_URL,
            "SCENEWEAVER_LLM_MODEL": LLM_MODEL,
            "SCENEWEAVER_LLM_MAX_TOKENS": str(LLM_MAX_TOKENS),
            "SCENEWEAVER_LLM_TEMPERATURE": str(LLM_TEMPERATURE),
            "SCENEWEAVER_LLM_RETRY_ATTEMPTS": str(LLM_RETRY_ATTEMPTS),
            "SCENEWEAVER_LLM_RETRY_MIN_DELAY_S": str(LLM_RETRY_MIN_DELAY_S),
            "SCENEWEAVER_LLM_RETRY_MAX_DELAY_S": str(LLM_RETRY_MAX_DELAY_S),
            "SCENEWEAVER_PREVIEW_WIDTH": str(PREVIEW_RESOLUTION[0]),
            "SCENEWEAVER_PREVIEW_HEIGHT": str(PREVIEW_RESOLUTION[1]),
            "SCENEWEAVER_PREVIEW_SAMPLES": str(PREVIEW_SAMPLES),
        }
    )
    return env


def run_logged(
    command: list[str],
    log_path: Path,
    env: dict[str, str],
    cwd: Path,
    timeout_s: int,
) -> tuple[int, float, bool]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    timed_out = False
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write("COMMAND_JSON=" + json.dumps(command, ensure_ascii=False) + "\n")
        log.flush()
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            exit_code = process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.terminate()
            try:
                exit_code = process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                exit_code = process.wait()
    return exit_code, time.monotonic() - started, timed_out


def logs_have_traceback(paths: list[Path]) -> bool:
    return any(
        "Traceback (most recent call last):"
        in path.read_text(encoding="utf-8", errors="replace")
        for path in paths
        if path.is_file()
    )


def final_scene_candidate(work_dir: Path) -> tuple[int, Path, Path] | None:
    # Upstream snapshots ``args.json`` to ``args/args_N.json`` *before* the
    # executor runs, then writes the success flag only to the live file.  The
    # archived copy therefore says false even on a successful iteration.
    live_args = work_dir / "args.json"
    if not live_args.is_file():
        return None
    try:
        args_payload = json.loads(live_args.read_text(encoding="utf-8"))
        index = int(args_payload["iter"])
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None
    scene_path = work_dir / "record_files" / f"scene_{index}.blend"
    layout_path = work_dir / "record_scene" / f"layout_{index}.json"
    if (
        args_payload.get("action") == "finalize_scene"
        and args_payload.get("success") is True
        and scene_path.is_file()
        and scene_path.stat().st_size > 1024 * 1024
        and layout_path.is_file()
    ):
        return index, scene_path, layout_path
    return None


def link_or_copy(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    try:
        os.link(source, destination)
        return "hardlink"
    except OSError:
        shutil.copy2(source, destination)
        return "copy"


def initialize_run(
    spec: dict[str, Any], logical_seed: int, spec_file: Path, data_root: Path
) -> tuple[Path, dict[str, Any]]:
    run_dir = (
        data_root / "indoor/sceneweaver" / spec["spec_id"] / f"seed_{logical_seed}"
    )
    assert_below_baselines(run_dir)
    (run_dir / "input").mkdir(parents=True, exist_ok=True)
    atomic_json(run_dir / "input/spec.json", spec)
    atomic_json(
        run_dir / "input/native_input.json", build_native_input(spec, logical_seed)
    )
    manifest_path = run_dir / "run_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {
            "method": "sceneweaver",
            "domain": "indoor",
            "spec_id": spec["spec_id"],
            "spec_index": spec["spec_index"],
            "logical_seed": logical_seed,
            "method_seed": method_seed(spec, logical_seed),
            "hardware": {"hostname": platform.node(), "gpu_index": None},
            "attempts": [],
            "generation_success": False,
            "render_success": False,
            "failure_reason": None,
        }
    manifest.update(
        {
            "spec_sha256": sha256_file(spec_file),
            "protocol_sha256": sha256_file(PROTOCOL_FILE),
            "upstream_commit": UPSTREAM_COMMIT,
            "patched_source_sha256": source_hashes(),
            "adapter_sha256": sha256_file(Path(__file__)),
            "renderer_sha256": (
                sha256_file(BLENDER_RENDER_SCRIPT)
                if BLENDER_RENDER_SCRIPT.is_file()
                else None
            ),
            "asset_index_sha256": sha256_file(ASSET_INDEX),
            "planner_python": str(PLANNER_PYTHON),
            "executor_python": str(EXECUTOR_PYTHON),
            "blender": {"path": str(BLENDER_BIN), "version": "4.2.0"},
            "llm": {
                "api_type": LLM_API_TYPE,
                "base_url": LLM_BASE_URL,
                "model": LLM_MODEL,
                "temperature": LLM_TEMPERATURE,
                "max_tokens": LLM_MAX_TOKENS,
                "max_attempts": PLANNER_MAX_ATTEMPTS,
                "transport_retry": {
                    "attempts": LLM_RETRY_ATTEMPTS,
                    "min_delay_s": LLM_RETRY_MIN_DELAY_S,
                    "max_delay_s": LLM_RETRY_MAX_DELAY_S,
                    "backoff": "exponential_without_jitter",
                },
                "seed_supported": False,
                "api_key_file": str(API_KEY_FILE),
                "api_key_recorded": False,
            },
            "planner_preview": {
                "resolution": list(PREVIEW_RESOLUTION),
                "cycles_samples": PREVIEW_SAMPLES,
                "denoise": True,
                "used_for_table2_metrics": False,
            },
        }
    )
    atomic_json(manifest_path, manifest)
    return run_dir, manifest


def inspect_images(run_dir: Path) -> dict[str, Any]:
    from PIL import Image, ImageStat

    anchors = sorted((run_dir / "renders/anchors").glob("rgb_*.png"))
    sequence = sorted((run_dir / "renders/sequence").glob("rgb_*.png"))
    image_records: list[dict[str, Any]] = []
    valid_images = True
    for path, expected in [(p, (1280, 720)) for p in anchors] + [
        (p, (512, 512)) for p in sequence
    ]:
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            stats = ImageStat.Stat(rgb)
            mean = sum(stats.mean) / (3.0 * 255.0)
            std = sum(stats.stddev) / (3.0 * 255.0)
            image_records.append(
                {
                    "path": str(path.relative_to(run_dir)),
                    "size": list(rgb.size),
                    "mean": mean,
                    "std": std,
                }
            )
            valid_images &= (
                rgb.size == expected and 0.01 <= mean <= 0.99 and std >= 0.01
            )

    cameras_path = run_dir / "renders/sequence/cameras.json"
    trajectory = {
        "valid": False,
        "frame_count": 0,
        "path_length_m": 0.0,
        "max_displacement_from_first_m": 0.0,
        "max_height_error_m": None,
    }
    if cameras_path.is_file():
        payload = json.loads(cameras_path.read_text(encoding="utf-8"))
        records = payload.get("sequence", [])
        centers = [
            [float(record["camera_to_world_blender"][row][3]) for row in range(3)]
            for record in records
        ]
        if centers:
            distance = lambda a, b: math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
            path_length = sum(distance(a, b) for a, b in zip(centers, centers[1:]))
            displacement = max(distance(centers[0], center) for center in centers)
            height_error = max(
                abs(center[2] - CAMERA_HEIGHT_METERS) for center in centers
            )
            contract_ok = payload.get("camera_pose_contract") == {
                "algorithm": "deterministic_free_space_grid_v1",
                "camera_height_m": CAMERA_HEIGHT_METERS,
                "collision_clearance_m": 0.3,
                "remove_roll_with_global_up": True,
            }
            trajectory.update(
                {
                    "frame_count": len(centers),
                    "path_length_m": path_length,
                    "max_displacement_from_first_m": displacement,
                    "max_height_error_m": height_error,
                    "valid": len(centers) == 50
                    and path_length >= 1.0
                    and displacement >= 0.5
                    and height_error <= 1e-4
                    and contract_ok,
                }
            )
    valid = (
        valid_images
        and len(anchors) == 8
        and len(sequence) == 50
        and cameras_path.is_file()
        and trajectory["valid"]
    )
    return {
        "valid": bool(valid),
        "anchor_count": len(anchors),
        "sequence_count": len(sequence),
        "cameras_json": cameras_path.is_file(),
        "trajectory": trajectory,
        "images": image_records,
    }


def generate(
    spec: dict[str, Any],
    logical_seed: int,
    spec_file: Path,
    data_root: Path,
    gpu: int,
    timeout_s: int,
    force: bool,
) -> bool:
    run_dir, manifest = initialize_run(spec, logical_seed, spec_file, data_root)
    scene_file = run_dir / "scene/scene.blend"
    marker = run_dir / "GENERATION_SUCCESS"
    if marker.is_file() and scene_file.is_file() and not force:
        print(f"SKIP generation {spec['spec_id']} seed={logical_seed}")
        return True

    for stale in (
        run_dir / "sceneweaver",
        run_dir / "scene",
        run_dir / "renders",
        run_dir / "metrics",
    ):
        if stale.exists():
            shutil.rmtree(stale)
    marker.unlink(missing_ok=True)
    (run_dir / "SUCCESS").unlink(missing_ok=True)
    work_dir = run_dir / "sceneweaver"
    attempt_index = 1 + sum(a.get("phase") == "generate" for a in manifest["attempts"])
    log_path = run_dir / f"logs/generate_attempt_{attempt_index:02d}.log"
    command = [
        str(PLANNER_PYTHON),
        str(PIPELINE_ROOT / "main.py"),
        "--prompt",
        spec["prompt_en"],
        "--save-dir",
        str(work_dir),
        "--seed",
        str(method_seed(spec, logical_seed)),
    ]
    started_at = utc_now()
    exit_code, wall_time, timed_out = run_logged(
        command, log_path, baseline_environment(gpu), PIPELINE_ROOT, timeout_s
    )
    candidate = final_scene_candidate(work_dir)
    all_logs = [log_path, *sorted((work_dir / "logs").glob("*.log"))]
    has_traceback = logs_have_traceback(all_logs)
    success = (
        exit_code == 0 and not timed_out and not has_traceback and candidate is not None
    )
    selected: dict[str, Any] | None = None
    if success and candidate is not None:
        iteration, source_scene, source_layout = candidate
        link_mode = link_or_copy(source_scene, scene_file)
        shutil.copy2(source_layout, run_dir / "scene/layout.json")
        selected = {
            "iteration": iteration,
            "source_scene": str(source_scene.relative_to(run_dir)),
            "source_layout": str(source_layout.relative_to(run_dir)),
            "scene_materialization": link_mode,
            "scene_size_bytes": scene_file.stat().st_size,
            "scene_sha256": sha256_file(scene_file),
        }

    attempt = {
        "phase": "generate",
        "started_at_utc": started_at,
        "ended_at_utc": utc_now(),
        "wall_time_s": wall_time,
        "gpu_index": gpu,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "traceback_in_logs": has_traceback,
        "log": str(log_path.relative_to(run_dir)),
        "command": command,
        "adapter_sha256": sha256_file(Path(__file__)),
        "native_input_sha256": sha256_file(run_dir / "input/native_input.json"),
        "patched_source_sha256": source_hashes(),
        "selected_output": selected,
        "success": success,
    }
    manifest["attempts"].append(attempt)
    manifest["hardware"]["gpu_index"] = gpu
    manifest["generation_success"] = success
    manifest["render_success"] = False
    manifest["failure_reason"] = None if success else "generation_failed"
    atomic_json(run_dir / "run_manifest.json", manifest)
    if success:
        marker.touch()
    print(
        f"GENERATION {'OK' if success else 'FAILED'} {spec['spec_id']} "
        f"seed={logical_seed} method_seed={method_seed(spec, logical_seed)} wall={wall_time:.1f}s"
    )
    return success


def render(
    spec: dict[str, Any],
    logical_seed: int,
    spec_file: Path,
    data_root: Path,
    gpu: int,
    timeout_s: int,
    force: bool,
) -> bool:
    run_dir, manifest = initialize_run(spec, logical_seed, spec_file, data_root)
    scene_file = run_dir / "scene/scene.blend"
    layout_file = run_dir / "scene/layout.json"
    if not scene_file.is_file() or not layout_file.is_file():
        print(
            f"RENDER FAILED missing generated scene/layout in {run_dir}",
            file=sys.stderr,
        )
        return False
    marker = run_dir / "SUCCESS"
    if marker.is_file() and not force:
        print(f"SKIP render {spec['spec_id']} seed={logical_seed}")
        return True
    marker.unlink(missing_ok=True)
    for stale in (run_dir / "renders", run_dir / "metrics"):
        if stale.exists():
            shutil.rmtree(stale)
    attempt_index = 1 + sum(a.get("phase") == "render" for a in manifest["attempts"])
    log_path = run_dir / f"logs/render_attempt_{attempt_index:02d}.log"
    command = [
        str(BLENDER_BIN),
        "-noaudio",
        "--background",
        str(scene_file),
        "--python",
        str(BLENDER_RENDER_SCRIPT),
        "--",
        "--run-dir",
        str(run_dir),
        "--gpu",
        str(gpu),
    ]
    started_at = utc_now()
    exit_code, wall_time, timed_out = run_logged(
        command, log_path, baseline_environment(gpu), SCENEWEAVER_ROOT, timeout_s
    )
    has_traceback = logs_have_traceback([log_path])
    validation = (
        inspect_images(run_dir)
        if exit_code == 0 and not timed_out
        else {
            "valid": False,
            "anchor_count": 0,
            "sequence_count": 0,
            "cameras_json": False,
            "trajectory": {"valid": False},
            "images": [],
        }
    )
    atomic_json(run_dir / "renders/validation.json", validation)
    success = (
        exit_code == 0 and not timed_out and not has_traceback and validation["valid"]
    )
    manifest["attempts"].append(
        {
            "phase": "render",
            "started_at_utc": started_at,
            "ended_at_utc": utc_now(),
            "wall_time_s": wall_time,
            "gpu_index": gpu,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "traceback_in_logs": has_traceback,
            "log": str(log_path.relative_to(run_dir)),
            "command": command,
            "adapter_sha256": sha256_file(Path(__file__)),
            "renderer_sha256": sha256_file(BLENDER_RENDER_SCRIPT),
            "success": success,
        }
    )
    manifest["render_success"] = success
    manifest["failure_reason"] = None if success else "render_or_validation_failed"
    atomic_json(run_dir / "run_manifest.json", manifest)
    if success:
        marker.touch()
    print(
        f"RENDER {'OK' if success else 'FAILED'} {spec['spec_id']} seed={logical_seed} wall={wall_time:.1f}s"
    )
    return success


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec-file", type=Path, default=DEFAULT_SPEC_FILE)
    parser.add_argument("--spec-id", required=True)
    parser.add_argument("--seed", type=int, required=True, dest="logical_seed")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--phase", choices=("generate", "render", "all"), default="all")
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--generation-timeout-s", type=int, default=21600)
    parser.add_argument("--render-timeout-s", type=int, default=10800)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def verify_prerequisites() -> None:
    required = (
        SCENEWEAVER_ROOT,
        PIPELINE_ROOT / "main.py",
        PLANNER_PYTHON,
        EXECUTOR_PYTHON,
        API_KEY_FILE,
        ASSET_INDEX,
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing SceneWeaver prerequisites: " + ", ".join(missing)
        )


def main() -> int:
    args = parse_args()
    # Child processes run from the vendored Pipeline/Infinigen directories.
    # Resolve user-supplied paths once so their meaning cannot change with cwd.
    args.spec_file = args.spec_file.expanduser().resolve()
    args.data_root = args.data_root.expanduser().resolve()
    verify_prerequisites()
    assert_below_baselines(args.data_root)
    specs = load_specs(args.spec_file)
    if args.spec_id not in specs:
        raise KeyError(f"Unknown spec_id={args.spec_id!r}")
    spec = specs[args.spec_id]
    ok = True
    if args.phase in ("generate", "all"):
        ok = generate(
            spec,
            args.logical_seed,
            args.spec_file,
            args.data_root,
            args.gpu,
            args.generation_timeout_s,
            args.force,
        )
    if ok and args.phase in ("render", "all"):
        if not BLENDER_RENDER_SCRIPT.is_file() or not BLENDER_BIN.is_file():
            raise FileNotFoundError("SceneWeaver renderer or Blender binary is missing")
        ok = render(
            spec,
            args.logical_seed,
            args.spec_file,
            args.data_root,
            args.gpu,
            args.render_timeout_s,
            args.force,
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
