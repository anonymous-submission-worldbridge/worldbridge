#!/usr/bin/env python3
"""Deterministic Table-2 adapter for Infinigen Indoors.

All generated state is kept below ``baselines/``.  Infinigen is treated as a
read-only source tree and Blender is launched as a Python module because the
official indoor entry point uses package-relative imports.
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
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES_ROOT = REPO_ROOT / "baselines"
INFINIGEN_ROOT = REPO_ROOT / "infinigen"
BLENDER_BIN = Path(_wb_expand_paths("${BLENDER_BIN}"))
INFINIGEN_ENV = Path(_wb_expand_paths("${WORLDBRIDGE_EXTERNAL}/envs/infinigen"))
SITE_PACKAGES = INFINIGEN_ENV / "lib/python3.11/site-packages"
BLENDER_RENDER_SCRIPT = (
    BASELINES_ROOT / "methods/infinigen/tools/blender_render_infinigen.py"
)
PATCH_ROOT = BASELINES_ROOT / "patches"
RUNTIME_PATCH = (
    PATCH_ROOT / "../methods/infinigen/patches/infinigen_duplicate_addition_name.py"
)
CONCRETE_WALL_PATCH = (
    PATCH_ROOT / "../methods/infinigen/patches/infinigen_concrete_wall_kwargs.py"
)
DEFAULT_SPEC_FILE = BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"
DEFAULT_DATA_ROOT = BASELINES_ROOT / "data/table2"
CAMERA_HEIGHT_METERS = 1.55
CAMERA_POSE_TOLERANCE = 1e-4


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
        raise ValueError("Table-2 logical_seed must be one of 0,1,2,3")
    return int(spec["spec_index"]) * 4 + logical_seed


def build_native_input(spec: dict[str, Any], logical_seed: int) -> dict[str, Any]:
    return {
        "adapter": "infinigen_indoors",
        "spec_id": spec["spec_id"],
        "logical_seed": logical_seed,
        "method_seed": method_seed(spec, logical_seed),
        "native_room_type": spec["native_room_type"],
        "compiled_fields": ["category"],
        "unsupported_native_fields": ["prompt_en", "extent_m", "required_facts"],
        "configs": [
            "singleroom.gin",
            "rrt_cam_indoors.gin",
            "real_geometry_with_bump.gin",
        ],
        "overrides": {
            "compose_indoors.terrain_enabled": False,
            # The official room OcMesher densifies the structural shell against
            # every trajectory pose.  With the frozen 50-frame protocol this
            # produced >12.9M vertices for a single shell and was repeatedly
            # killed during the pilot.  Keep the original room mesh while
            # retaining all furniture, materials and solver settings.
            "compose_indoors.enable_ocmesh_room": False,
            "compose_indoors.solve_steps_large": 300,
            "compose_indoors.solve_steps_medium": 200,
            "compose_indoors.solve_steps_small": 50,
            "execute_tasks.frame_range": [1, 50],
            "restrict_solving.restrict_parent_rooms": [spec["native_room_type"]],
            "blender.use_file_compression": True,
        },
    }


def baseline_environment(gpu: int) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "CUDA_VISIBLE_DEVICES": str(gpu),
            "PYTHONPATH": os.pathsep.join((str(INFINIGEN_ROOT), str(SITE_PACKAGES))),
            "PYTHONPYCACHEPREFIX": str(BASELINES_ROOT / "cache/pycache"),
            "MPLCONFIGDIR": str(BASELINES_ROOT / "cache/matplotlib"),
            "XDG_CACHE_HOME": str(BASELINES_ROOT / "cache/xdg"),
            "XDG_CONFIG_HOME": str(BASELINES_ROOT / "cache/config"),
            "HF_HOME": str(BASELINES_ROOT / "cache/huggingface"),
            "TORCH_HOME": str(BASELINES_ROOT / "cache/torch"),
        }
    )
    return env


def run_logged(
    command: list[str], log_path: Path, env: dict[str, str], timeout_s: int
) -> tuple[int, float, bool]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    timed_out = False
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write("COMMAND_JSON=" + json.dumps(command, ensure_ascii=False) + "\n")
        log.flush()
        process = subprocess.Popen(
            command,
            cwd=INFINIGEN_ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
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


def log_has_traceback(path: Path) -> bool:
    if not path.exists():
        return True
    return "Traceback (most recent call last):" in path.read_text(
        encoding="utf-8", errors="replace"
    )


def inspect_images(run_dir: Path) -> dict[str, Any]:
    from PIL import Image, ImageStat

    anchors = sorted((run_dir / "renders/anchors").glob("rgb_*.png"))
    sequence = sorted((run_dir / "renders/sequence").glob("rgb_*.png"))
    records: list[dict[str, Any]] = []
    valid = True
    for path in anchors:
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            stats = ImageStat.Stat(rgb)
            mean = sum(stats.mean) / (3.0 * 255.0)
            std = sum(stats.stddev) / (3.0 * 255.0)
            records.append(
                {
                    "path": str(path.relative_to(run_dir)),
                    "size": list(rgb.size),
                    "mean": mean,
                    "std": std,
                }
            )
            if rgb.size != (1280, 720) or not (0.01 <= mean <= 0.99 and std >= 0.01):
                valid = False
    for path in sequence:
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            stats = ImageStat.Stat(rgb)
            mean = sum(stats.mean) / (3.0 * 255.0)
            std = sum(stats.stddev) / (3.0 * 255.0)
            records.append(
                {
                    "path": str(path.relative_to(run_dir)),
                    "size": list(rgb.size),
                    "mean": mean,
                    "std": std,
                }
            )
            if rgb.size != (512, 512) or not (0.01 <= mean <= 0.99 and std >= 0.01):
                valid = False
    cameras = run_dir / "renders/sequence/cameras.json"
    trajectory = {
        "valid": False,
        "pose_contract_valid": False,
        "frame_count": 0,
        "path_length_m": 0.0,
        "max_displacement_from_first_m": 0.0,
        "camera_height_m": CAMERA_HEIGHT_METERS,
        "max_height_error_m": None,
        "max_roll_axis_vertical_component": None,
        "max_source_xy_error_m": None,
        "max_source_forward_error": None,
        "min_path_length_m": 1.0,
        "min_max_displacement_m": 0.5,
    }
    if cameras.exists():
        camera_payload = json.loads(cameras.read_text(encoding="utf-8"))
        camera_records = camera_payload.get("sequence", [])
        camera_matrices = [
            record["camera_to_world_blender"] for record in camera_records
        ]
        centers = [
            [float(matrix[row][3]) for row in range(3)] for matrix in camera_matrices
        ]
        if centers:
            distance = lambda a, b: math.sqrt(
                sum((left - right) ** 2 for left, right in zip(a, b))
            )
            path_length = sum(
                distance(previous, current)
                for previous, current in zip(centers, centers[1:])
            )
            max_displacement = max(distance(centers[0], center) for center in centers)
            max_height_error = max(
                abs(center[2] - CAMERA_HEIGHT_METERS) for center in centers
            )
            max_roll_axis_vertical = max(
                abs(float(matrix[2][0])) for matrix in camera_matrices
            )
            source_matrices = [
                record.get("source_camera_to_world_blender")
                for record in camera_records
            ]
            source_pose_complete = all(matrix is not None for matrix in source_matrices)
            source_xy_errors: list[float] = []
            source_forward_errors: list[float] = []
            if source_pose_complete:
                for matrix, source in zip(camera_matrices, source_matrices):
                    source_xy_errors.append(
                        math.sqrt(
                            (float(matrix[0][3]) - float(source[0][3])) ** 2
                            + (float(matrix[1][3]) - float(source[1][3])) ** 2
                        )
                    )
                    forward = [-float(matrix[row][2]) for row in range(3)]
                    source_forward = [-float(source[row][2]) for row in range(3)]
                    source_forward_errors.append(
                        math.sqrt(
                            sum(
                                (left - right) ** 2
                                for left, right in zip(forward, source_forward)
                            )
                        )
                    )
            max_source_xy_error = max(source_xy_errors, default=float("inf"))
            max_source_forward_error = max(source_forward_errors, default=float("inf"))
            expected_contract = {
                "camera_height_m": CAMERA_HEIGHT_METERS,
                "preserve_source_xy": True,
                "preserve_source_forward": True,
                "remove_roll_with_global_up": True,
            }
            pose_contract_valid = (
                camera_payload.get("camera_pose_contract") == expected_contract
                and source_pose_complete
                and max_height_error <= CAMERA_POSE_TOLERANCE
                and max_roll_axis_vertical <= CAMERA_POSE_TOLERANCE
                and max_source_xy_error <= CAMERA_POSE_TOLERANCE
                and max_source_forward_error <= CAMERA_POSE_TOLERANCE
            )
            trajectory.update(
                {
                    "frame_count": len(centers),
                    "path_length_m": path_length,
                    "max_displacement_from_first_m": max_displacement,
                    "pose_contract_valid": pose_contract_valid,
                    "max_height_error_m": max_height_error,
                    "max_roll_axis_vertical_component": max_roll_axis_vertical,
                    "max_source_xy_error_m": max_source_xy_error,
                    "max_source_forward_error": max_source_forward_error,
                    "valid": len(centers) == 50
                    and path_length >= trajectory["min_path_length_m"]
                    and max_displacement >= trajectory["min_max_displacement_m"]
                    and pose_contract_valid,
                }
            )
    valid = (
        valid
        and len(anchors) == 8
        and len(sequence) == 50
        and cameras.exists()
        and trajectory["valid"]
    )
    return {
        "valid": valid,
        "anchor_count": len(anchors),
        "sequence_count": len(sequence),
        "cameras_json": cameras.exists(),
        "trajectory": trajectory,
        "images": records,
    }


def initialize_run(
    spec: dict[str, Any], logical_seed: int, data_root: Path
) -> tuple[Path, dict[str, Any]]:
    run_dir = (
        data_root
        / "indoor"
        / "infinigen_indoors"
        / spec["spec_id"]
        / f"seed_{logical_seed}"
    )
    input_dir = run_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(input_dir / "spec.json", spec)
    native_path = input_dir / "native_input.json"
    if not native_path.exists():
        atomic_json(native_path, build_native_input(spec, logical_seed))
    manifest_path = run_dir / "run_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {
            "method": "infinigen_indoors",
            "domain": "indoor",
            "spec_id": spec["spec_id"],
            "spec_index": spec["spec_index"],
            "logical_seed": logical_seed,
            "method_seed": method_seed(spec, logical_seed),
            "spec_sha256": sha256_file(DEFAULT_SPEC_FILE),
            "infinigen_version": "1.19.1",
            "upstream_reference_commit": "05a09759fe9478595a3323ec2d6e26ce3513223f",
            "local_source_snapshot_sha256": "a33d7cc0a70b87c66d3702a0b775f0cc50027edc2432a848f29a17495fdae1eb",
            "blender_version": "4.2.0",
            "hardware": {"hostname": platform.node(), "gpu_index": None},
            "attempts": [],
            "generation_success": False,
            "render_success": False,
            "failure_reason": None,
        }
    # Backfill immutable provenance when resuming manifests made by an older
    # adapter revision.  These fields are refreshed, not inherited silently.
    manifest.update(
        {
            "infinigen_version": "1.19.1",
            "upstream_reference_commit": "05a09759fe9478595a3323ec2d6e26ce3513223f",
            "local_source_snapshot_sha256": "a33d7cc0a70b87c66d3702a0b775f0cc50027edc2432a848f29a17495fdae1eb",
            "adapter_sha256": sha256_file(Path(__file__)),
            "renderer_sha256": sha256_file(BLENDER_RENDER_SCRIPT),
            "runtime_patch_sha256": sha256_file(RUNTIME_PATCH),
            "concrete_wall_patch_sha256": sha256_file(CONCRETE_WALL_PATCH),
            "protocol_sha256": sha256_file(
                (BASELINES_ROOT / "protocol/generation/protocol.yaml")
            ),
        }
    )
    atomic_json(manifest_path, manifest)
    return run_dir, manifest


def generate(
    spec: dict[str, Any],
    logical_seed: int,
    data_root: Path,
    gpu: int,
    timeout_s: int,
    force: bool,
) -> bool:
    run_dir, manifest = initialize_run(spec, logical_seed, data_root)
    scene_dir = run_dir / "scene"
    scene_file = scene_dir / "scene.blend"
    marker = run_dir / "GENERATION_SUCCESS"
    if marker.exists() and scene_file.exists() and not force:
        print(f"SKIP generation {spec['spec_id']} seed={logical_seed}")
        return True
    atomic_json(
        run_dir / "input/native_input.json", build_native_input(spec, logical_seed)
    )
    # A new generation attempt must never inherit a partial scene or stale
    # render marker.  Attempt logs/manifests remain untouched for auditability.
    marker.unlink(missing_ok=True)
    (run_dir / "SUCCESS").unlink(missing_ok=True)
    if scene_dir.exists():
        shutil.rmtree(scene_dir)
    renders_dir = run_dir / "renders"
    if renders_dir.exists():
        shutil.rmtree(renders_dir)
    metrics_dir = run_dir / "metrics"
    if metrics_dir.exists():
        shutil.rmtree(metrics_dir)
    scene_dir.mkdir(parents=True, exist_ok=True)
    # Capture provenance before the long-running subprocess.  Otherwise a
    # pilot compatibility revision installed while another worker is active
    # could be recorded as if the older worker had used it.
    adapter_sha256 = sha256_file(Path(__file__))
    runtime_patch_sha256 = sha256_file(RUNTIME_PATCH)
    concrete_wall_patch_sha256 = sha256_file(CONCRETE_WALL_PATCH)
    attempt_index = 1 + sum(
        attempt.get("phase") == "generate" for attempt in manifest["attempts"]
    )
    log_path = run_dir / f"logs/generate_attempt_{attempt_index:02d}.log"
    override_room = (
        'restrict_solving.restrict_parent_rooms=["' + spec["native_room_type"] + '"]'
    )
    command = [
        str(BLENDER_BIN),
        "-noaudio",
        "--background",
        "--python-use-system-env",
        "--python-expr",
        (
            "import bpy,runpy,sys; "
            "bpy.context.preferences.filepaths.use_file_compression=True; "
            f"sys.path.insert(0,{str(PATCH_ROOT)!r}); "
            "from infinigen_duplicate_addition_name import apply_patch; "
            "apply_patch(); "
            "from infinigen_concrete_wall_kwargs import apply_patch as apply_concrete_patch; "
            "apply_concrete_patch(); "
            "runpy.run_module('infinigen_examples.generate_indoors', run_name='__main__')"
        ),
        "--",
        "--seed",
        str(method_seed(spec, logical_seed)),
        "--task",
        "coarse",
        "--output_folder",
        str(scene_dir),
        "-g",
        "singleroom.gin",
        "rrt_cam_indoors.gin",
        "real_geometry_with_bump.gin",
        "-p",
        "compose_indoors.terrain_enabled=False",
        "compose_indoors.enable_ocmesh_room=False",
        "compose_indoors.solve_steps_large=300",
        "compose_indoors.solve_steps_medium=200",
        "compose_indoors.solve_steps_small=50",
        "execute_tasks.frame_range=[1,50]",
        override_room,
    ]
    started_at = utc_now()
    exit_code, wall_time, timed_out = run_logged(
        command, log_path, baseline_environment(gpu), timeout_s
    )
    success = (
        exit_code == 0
        and not timed_out
        and scene_file.exists()
        and scene_file.stat().st_size > 1024 * 1024
        and not log_has_traceback(log_path)
    )
    attempt = {
        "phase": "generate",
        "adapter_sha256": adapter_sha256,
        "runtime_patch_sha256": runtime_patch_sha256,
        "concrete_wall_patch_sha256": concrete_wall_patch_sha256,
        "protocol_sha256": sha256_file(
            (BASELINES_ROOT / "protocol/generation/protocol.yaml")
        ),
        "native_input_sha256": sha256_file(run_dir / "input/native_input.json"),
        "started_at_utc": started_at,
        "ended_at_utc": utc_now(),
        "wall_time_s": wall_time,
        "gpu_index": gpu,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "log": str(log_path.relative_to(run_dir)),
        "command": command,
        "success": success,
    }
    manifest["attempts"].append(attempt)
    manifest["hardware"]["gpu_index"] = gpu
    manifest["generation_success"] = success
    manifest["failure_reason"] = None if success else "generation_failed"
    atomic_json(run_dir / "run_manifest.json", manifest)
    if success:
        marker.touch()
    print(
        f"GENERATION {'OK' if success else 'FAILED'} {spec['spec_id']} "
        f"seed={logical_seed} method_seed={method_seed(spec, logical_seed)} "
        f"wall={wall_time:.1f}s"
    )
    return success


def render(
    spec: dict[str, Any],
    logical_seed: int,
    data_root: Path,
    gpu: int,
    timeout_s: int,
    force: bool,
) -> bool:
    run_dir, manifest = initialize_run(spec, logical_seed, data_root)
    scene_file = run_dir / "scene/scene.blend"
    if not scene_file.exists():
        print(f"RENDER FAILED missing scene: {scene_file}", file=sys.stderr)
        return False
    marker = run_dir / "SUCCESS"
    if marker.exists() and not force:
        print(f"SKIP render {spec['spec_id']} seed={logical_seed}")
        return True
    renders_dir = run_dir / "renders"
    marker.unlink(missing_ok=True)
    if renders_dir.exists():
        shutil.rmtree(renders_dir)
    metrics_dir = run_dir / "metrics"
    if metrics_dir.exists():
        shutil.rmtree(metrics_dir)
    attempt_index = 1 + sum(
        attempt.get("phase") == "render" for attempt in manifest["attempts"]
    )
    log_path = run_dir / f"logs/render_attempt_{attempt_index:02d}.log"
    command = [
        str(BLENDER_BIN),
        "-noaudio",
        "--background",
        str(scene_file),
        "--python-use-system-env",
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
        command, log_path, baseline_environment(gpu), timeout_s
    )
    validation = (
        inspect_images(run_dir)
        if exit_code == 0 and not timed_out
        else {
            "valid": False,
            "anchor_count": 0,
            "sequence_count": 0,
            "cameras_json": False,
            "images": [],
        }
    )
    atomic_json(run_dir / "renders/validation.json", validation)
    success = (
        exit_code == 0
        and not timed_out
        and not log_has_traceback(log_path)
        and validation["valid"]
    )
    attempt = {
        "phase": "render",
        "adapter_sha256": sha256_file(Path(__file__)),
        "renderer_sha256": sha256_file(BLENDER_RENDER_SCRIPT),
        "protocol_sha256": sha256_file(
            (BASELINES_ROOT / "protocol/generation/protocol.yaml")
        ),
        "native_input_sha256": sha256_file(run_dir / "input/native_input.json"),
        "started_at_utc": started_at,
        "ended_at_utc": utc_now(),
        "wall_time_s": wall_time,
        "gpu_index": gpu,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "log": str(log_path.relative_to(run_dir)),
        "command": command,
        "success": success,
    }
    manifest["attempts"].append(attempt)
    manifest["render_success"] = success
    manifest["failure_reason"] = None if success else "render_or_validation_failed"
    atomic_json(run_dir / "run_manifest.json", manifest)
    if success:
        marker.touch()
    print(
        f"RENDER {'OK' if success else 'FAILED'} {spec['spec_id']} "
        f"seed={logical_seed} wall={wall_time:.1f}s"
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
    # Full-quality procedural assets can legitimately take more than three
    # hours to instantiate on dense scenes; this guard is infrastructure-only.
    parser.add_argument("--generation-timeout-s", type=int, default=43200)
    parser.add_argument("--render-timeout-s", type=int, default=10800)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    specs = load_specs(args.spec_file)
    if args.spec_id not in specs:
        raise KeyError(f"Unknown spec_id={args.spec_id!r}")
    spec = specs[args.spec_id]
    ok = True
    if args.phase in ("generate", "all"):
        ok = generate(
            spec,
            args.logical_seed,
            args.data_root,
            args.gpu,
            args.generation_timeout_s,
            args.force,
        )
    if ok and args.phase in ("render", "all"):
        ok = render(
            spec,
            args.logical_seed,
            args.data_root,
            args.gpu,
            args.render_timeout_s,
            args.force,
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
