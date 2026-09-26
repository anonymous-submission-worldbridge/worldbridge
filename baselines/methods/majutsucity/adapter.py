#!/usr/bin/env python3
"""Table-2 input adapter and native runner for MajutsuCity Urban."""

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
import heapq
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
SOURCE_ROOT = BASELINES_ROOT / "sources/MajutsuCity"
SPEC_FILE = BASELINES_ROOT / "protocol/generation/urban_specs.jsonl"
PROTOCOL_FILE = (
    BASELINES_ROOT / "methods/majutsucity/protocol/generation/majutsucity.yaml"
)
CONFIG_FILE = SOURCE_ROOT / "configs/paths.local.yaml"
NATIVE_OUTPUT_ROOT = BASELINES_ROOT / "data/majutsucity_native"
PILOT_DATA_ROOT = BASELINES_ROOT / "data/pilot"
FORMAL_DATA_ROOT = BASELINES_ROOT / "data/table2"
PYTHON = BASELINES_ROOT / "envs/majutsucity/bin/python"
GENERATE_CITY = SOURCE_ROOT / "scripts/generate_city.py"
BLENDER = Path(_wb_expand_paths("${BLENDER_BIN}"))
RENDERER = BASELINES_ROOT / "methods/majutsucity/tools/blender_render_majutsucity.py"
SOURCE_COMMIT = "8cd8c9847f901f087f16e7993c869e1077bad5f5"
STYLE = "european"
PILOT_SPEC_INDICES = (0, 6, 12, 18, 24)
TRAJECTORY_LENGTH_M = 42.0
CAMERA_HEIGHT_M = 1.65
LOOK_ROTATION_DEGREES = 75.0
FRAME_COUNT = 50
ANCHOR_INDICES = (0, 7, 14, 21, 28, 35, 42, 49)
PROXY_VARIABLES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
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


def archive_finished_native_attempt(destination: Path) -> Path | None:
    """Preserve a completed native command record before a same-seed retry."""
    command_path = destination / "native_command.json"
    if not command_path.is_file():
        return None
    record = json.loads(command_path.read_text(encoding="utf-8"))
    if "finished_at" not in record or "exit_code" not in record:
        return None
    started_at = str(record.get("started_at", "unknown")).replace(":", "-")
    archive_path = destination / "attempts" / f"native_command_{started_at}.json"
    if archive_path.exists():
        observed = json.loads(archive_path.read_text(encoding="utf-8"))
        if observed != record:
            raise FileExistsError(f"Attempt archive differs: {archive_path}")
    else:
        atomic_json(archive_path, record)
    return archive_path


def under_baselines(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(BASELINES_ROOT.resolve())
    except ValueError as error:
        raise ValueError(f"Path escapes baselines: {path}") from error
    return resolved


def load_specs() -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    with SPEC_FILE.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            spec = json.loads(line)
            if spec.get("domain") != "urban":
                raise ValueError(f"Non-urban spec on line {line_number}")
            specs.append(spec)
    if len(specs) != 25 or len({item["spec_id"] for item in specs}) != 25:
        raise ValueError("Expected 25 unique urban specifications")
    return specs


def load_spec(spec_id: str) -> dict[str, Any]:
    matches = [spec for spec in load_specs() if spec["spec_id"] == spec_id]
    if len(matches) != 1:
        raise ValueError(f"Unknown spec_id: {spec_id}")
    return matches[0]


def method_seed(spec: dict[str, Any], logical_seed: int) -> int:
    if logical_seed not in (0, 1, 2, 3):
        raise ValueError("Logical seed must be one of 0,1,2,3")
    return int(spec["spec_index"]) * 4 + logical_seed


def scene_plan(spec: dict[str, Any]) -> dict[str, str]:
    prompt = str(spec["prompt_en"]).strip()
    category = str(spec["category"]).replace("_", " ")
    topology = str(spec["topology"]).replace("_", " ")
    shared = (
        f"European architectural style. {prompt} Preserve the requested {topology} "
        "road topology, functional district identity, unobstructed circulation, "
        "and coherent city-wide materials."
    )
    return {
        "layout": (
            f"Top-down semantic city layout for a {category} district. {prompt} "
            "Use connected red roads, yellow building footprints, green vegetation, "
            "gray public ground, blue water only when requested, and black empty space."
        ),
        "building": (
            f"Generate one complete European-style building belonging to this coordinated "
            f"urban design: {shared} Isolate the building on a pure white background."
        ),
        "tree": (
            f"One complete realistic European streetscape tree suitable for this {category} "
            "district, isolated on a pure white background."
        ),
        "lamp": (
            "One complete realistic European urban street lamp at plausible pedestrian "
            "scale, isolated on a pure white background."
        ),
        "ground": f"A seamless realistic European {category} public-ground PBR texture.",
        "grass": "A seamless realistic temperate urban grass and planting PBR texture.",
        "road": (
            f"A seamless realistic European asphalt road PBR texture appropriate for a "
            f"{topology}, with restrained markings and no objects."
        ),
        "water": "A seamless realistic calm urban water PBR texture with subtle ripples.",
        "sky": "A seamless 2:1 realistic clear daytime European city skybox.",
    }


def plan_record(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": 1,
        "source_prompt": spec["prompt_en"],
        "style": STYLE,
        "plan": scene_plan(spec),
        "provider": {
            "protocol": "deterministic_table2_adapter",
            "model": None,
            "output_selection": "none",
            "template_version": "majutsucity-table2-scene-plan-v1",
        },
    }


def run_dir(trial_mode: str, spec: dict[str, Any], logical_seed: int) -> Path:
    root = PILOT_DATA_ROOT if trial_mode == "pilot" else FORMAL_DATA_ROOT
    return root / "urban/majutsucity" / spec["spec_id"] / f"seed_{logical_seed}"


def native_case_name(trial_mode: str, spec: dict[str, Any], logical_seed: int) -> str:
    return f"table2_{trial_mode}_{spec['spec_id']}_seed_{logical_seed}"


def native_case_dir(trial_mode: str, spec: dict[str, Any], logical_seed: int) -> Path:
    return NATIVE_OUTPUT_ROOT / native_case_name(trial_mode, spec, logical_seed)


def prepare_run(
    trial_mode: str, spec: dict[str, Any], logical_seed: int
) -> tuple[Path, Path]:
    destination = under_baselines(run_dir(trial_mode, spec, logical_seed))
    destination.mkdir(parents=True, exist_ok=True)
    input_dir = destination / "input"
    input_dir.mkdir(exist_ok=True)
    spec_path = input_dir / "spec.json"
    plan_path = input_dir / "scene_plan.json"
    native_input_path = input_dir / "native.json"
    native = {
        "adapter": "majutsucity",
        "adapter_policy": {
            "output_selection": "none",
            "retry_quality_failures": False,
            "prompt_tuning_after_output": False,
        },
        "spec_id": spec["spec_id"],
        "logical_seed": logical_seed,
        "method_seed": method_seed(spec, logical_seed),
        "style": STYLE,
        "scene_plan_mode": "deterministic_shared_spec_to_official_scene_plan",
        "scene_plan_template_version": "majutsucity-table2-scene-plan-v1",
        "official_options": {
            "generate_layout": True,
            "layout_palette": "auto",
            "edit_profile": "constrained",
            "execution_order": "phase",
            "shape_backend": "omni",
            "point_samples": 50,
            "building_scale_mode": "depth",
            "vlm_review": False,
            "allow_missing_buildings": False,
        },
    }
    expected = (
        (spec_path, spec),
        (plan_path, plan_record(spec)),
        (native_input_path, native),
    )
    for path, payload in expected:
        if path.exists():
            observed = json.loads(path.read_text(encoding="utf-8"))
            if observed != payload:
                raise FileExistsError(
                    f"Frozen input differs from existing file: {path}"
                )
        else:
            atomic_json(path, payload)
    manifest = {
        "method": "majutsucity",
        "domain": "urban",
        "trial_mode": trial_mode,
        "spec_id": spec["spec_id"],
        "logical_seed": logical_seed,
        "method_seed": method_seed(spec, logical_seed),
        "source_commit": SOURCE_COMMIT,
        "source_patch_sha256": {
            "layout_gen/demo.py": sha256_file(SOURCE_ROOT / "layout_gen/demo.py"),
            "scripts/preflight.py": sha256_file(SOURCE_ROOT / "scripts/preflight.py"),
            "scripts/run_pipeline.py": sha256_file(
                SOURCE_ROOT / "scripts/run_pipeline.py"
            ),
            "scripts/run_city_asset_pipeline.py": sha256_file(
                SOURCE_ROOT / "scripts/run_city_asset_pipeline.py"
            ),
            "scripts/run_hunyuan3d_local.py": sha256_file(
                SOURCE_ROOT / "scripts/run_hunyuan3d_local.py"
            ),
            "scripts/run_qwen_image_edit_local.py": sha256_file(
                SOURCE_ROOT / "scripts/run_qwen_image_edit_local.py"
            ),
            "scripts/run_style_environment_assets.py": sha256_file(
                SOURCE_ROOT / "scripts/run_style_environment_assets.py"
            ),
            "utils/qwen_lora_generation.py": sha256_file(
                SOURCE_ROOT / "utils/qwen_lora_generation.py"
            ),
            "utils/qwen_image.py": sha256_file(SOURCE_ROOT / "utils/qwen_image.py"),
        },
        "protocol_path": str(PROTOCOL_FILE),
        "protocol_sha256": sha256_file(PROTOCOL_FILE),
        "config_path": str(CONFIG_FILE),
        "config_sha256": sha256_file(CONFIG_FILE),
        "native_case_name": native_case_name(trial_mode, spec, logical_seed),
        "native_case_dir": str(native_case_dir(trial_mode, spec, logical_seed)),
        "created_at": utc_now(),
    }
    manifest_path = destination / "run_manifest.json"
    if manifest_path.exists():
        observed = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (destination / "SUCCESS").exists() and any(
            observed.get(key) != value
            for key, value in manifest.items()
            if key != "created_at"
        ):
            raise FileExistsError(
                f"Completed run manifest no longer matches frozen inputs: {manifest_path}"
            )
        manifest = {
            **observed,
            **manifest,
            "created_at": observed.get("created_at", manifest["created_at"]),
        }
    atomic_json(manifest_path, manifest)
    return destination, plan_path


def generation_command(
    trial_mode: str, spec: dict[str, Any], logical_seed: int, plan_path: Path
) -> list[str]:
    return [
        str(PYTHON),
        str(GENERATE_CITY),
        "--config",
        str(CONFIG_FILE),
        "--case-name",
        native_case_name(trial_mode, spec, logical_seed),
        "--style",
        STYLE,
        "--scene-plan",
        str(plan_path),
        "--seed",
        str(method_seed(spec, logical_seed)),
        "--layout-palette",
        "auto",
        "--edit-profile",
        "constrained",
        "--execution-order",
        "phase",
        "--shape-backend",
        "omni",
        "--point-samples",
        "50",
        "--building-scale-mode",
        "depth",
    ]


def _pixel_neighbors(
    pixel: tuple[int, int], nodes: set[tuple[int, int]]
) -> list[tuple[tuple[int, int], float]]:
    row, column = pixel
    result = []
    for row_offset in (-1, 0, 1):
        for column_offset in (-1, 0, 1):
            if row_offset == column_offset == 0:
                continue
            candidate = (row + row_offset, column + column_offset)
            if candidate in nodes:
                result.append((candidate, math.hypot(row_offset, column_offset)))
    return sorted(result)


def _components(nodes: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    unseen = set(nodes)
    components = []
    while unseen:
        start = min(unseen)
        component = {start}
        stack = [start]
        unseen.remove(start)
        while stack:
            for candidate, _ in _pixel_neighbors(stack.pop(), nodes):
                if candidate in unseen:
                    unseen.remove(candidate)
                    component.add(candidate)
                    stack.append(candidate)
        components.append(component)
    return components


def _dijkstra(
    start: tuple[int, int], nodes: set[tuple[int, int]]
) -> tuple[dict[tuple[int, int], float], dict[tuple[int, int], tuple[int, int]]]:
    distances = {start: 0.0}
    parents: dict[tuple[int, int], tuple[int, int]] = {}
    queue = [(0.0, start)]
    while queue:
        distance, current = heapq.heappop(queue)
        if distance != distances[current]:
            continue
        for candidate, edge_length in _pixel_neighbors(current, nodes):
            next_distance = distance + edge_length
            if next_distance < distances.get(candidate, float("inf")):
                distances[candidate] = next_distance
                parents[candidate] = current
                heapq.heappush(queue, (next_distance, candidate))
    return distances, parents


def _resample_polyline(
    points: list[tuple[float, float]], start_distance: float, end_distance: float
) -> list[tuple[float, float]]:
    cumulative = [0.0]
    for previous, current in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + math.dist(previous, current))
    result = []
    segment = 0
    for index in range(FRAME_COUNT):
        target = start_distance + (end_distance - start_distance) * index / (
            FRAME_COUNT - 1
        )
        while segment + 1 < len(cumulative) - 1 and cumulative[segment + 1] < target:
            segment += 1
        span = cumulative[segment + 1] - cumulative[segment]
        ratio = 0.0 if span == 0 else (target - cumulative[segment]) / span
        left, right = points[segment], points[segment + 1]
        result.append(
            (
                left[0] + ratio * (right[0] - left[0]),
                left[1] + ratio * (right[1] - left[1]),
            )
        )
    return result


def plan_camera_path(layout_path: Path, output_path: Path) -> dict[str, Any]:
    """Derive one deterministic 42 m eye-level path from the generated road mask."""
    import numpy as np
    from PIL import Image
    from skimage.morphology import skeletonize

    image = np.asarray(Image.open(layout_path).convert("RGB"), dtype=np.uint8)
    road_candidates = {
        "majutsu": np.all(image == np.asarray([255, 0, 0], dtype=np.uint8), axis=-1),
        "citydreamer": np.all(image == np.asarray([96, 0, 0], dtype=np.uint8), axis=-1),
    }
    palette = max(road_candidates, key=lambda name: int(road_candidates[name].sum()))
    road = road_candidates[palette]
    if int(road.sum()) == 0:
        raise RuntimeError(f"No exact road pixels found in {layout_path}")
    skeleton = skeletonize(road)
    nodes = {tuple(map(int, item)) for item in np.argwhere(skeleton)}
    if not nodes:
        raise RuntimeError(f"Road skeleton is empty in {layout_path}")
    component = max(_components(nodes), key=lambda value: (len(value), sorted(value)))
    center = ((image.shape[0] - 1) / 2.0, (image.shape[1] - 1) / 2.0)
    center_node = min(component, key=lambda p: (math.dist(p, center), p))
    first_distances, _ = _dijkstra(center_node, component)
    endpoint_a = max(first_distances, key=lambda p: (first_distances[p], p))
    second_distances, parents = _dijkstra(endpoint_a, component)
    endpoint_b = max(second_distances, key=lambda p: (second_distances[p], p))
    pixels = [endpoint_b]
    while pixels[-1] != endpoint_a:
        pixels.append(parents[pixels[-1]])
    pixels.reverse()
    image_points = [(float(column) + 0.5, float(row) + 0.5) for row, column in pixels]
    cumulative = [0.0]
    for previous, current in zip(image_points, image_points[1:]):
        cumulative.append(cumulative[-1] + math.dist(previous, current))
    diameter_length = cumulative[-1]
    if diameter_length < TRAJECTORY_LENGTH_M:
        raise RuntimeError(
            f"Largest road component has only {diameter_length:.3f} m of skeleton diameter"
        )
    center_index = min(
        range(len(image_points)),
        key=lambda index: (math.dist(image_points[index], center[::-1]), index),
    )
    start_distance = min(
        max(cumulative[center_index] - TRAJECTORY_LENGTH_M / 2.0, 0.0),
        diameter_length - TRAJECTORY_LENGTH_M,
    )
    path_xy_image = _resample_polyline(
        image_points, start_distance, start_distance + TRAJECTORY_LENGTH_M
    )
    path_world = [(x, -y) for x, y in path_xy_image]
    records = []
    for index, (x, y) in enumerate(path_world):
        before = path_world[max(0, index - 2)]
        after = path_world[min(FRAME_COUNT - 1, index + 2)]
        path_heading = math.atan2(after[1] - before[1], after[0] - before[0])
        alpha = index / (FRAME_COUNT - 1)
        view_heading = path_heading + math.radians(LOOK_ROTATION_DEGREES) * alpha
        records.append(
            {
                "frame_index": index + 1,
                "position_m": [x, y, CAMERA_HEIGHT_M],
                "path_heading_degrees": math.degrees(path_heading),
                "view_heading_degrees": math.degrees(view_heading),
            }
        )
    actual_length = sum(
        math.dist(left[:2], right[:2])
        for left, right in zip(
            (record["position_m"] for record in records),
            (record["position_m"] for record in records[1:]),
        )
    )
    max_displacement = max(
        math.dist(records[0]["position_m"][:2], record["position_m"][:2])
        for record in records
    )
    payload = {
        "camera_pose_contract": {
            "algorithm": "largest_road_skeleton_diameter_centered_42m_v1",
            "camera_height_m": CAMERA_HEIGHT_M,
            "look_rotation_degrees": LOOK_ROTATION_DEGREES,
            "road_palette": palette,
        },
        "path_planner": {
            "layout_resolution": [int(image.shape[1]), int(image.shape[0])],
            "road_pixel_count": int(road.sum()),
            "skeleton_pixel_count": len(nodes),
            "selected_component_size": len(component),
            "skeleton_diameter_m": diameter_length,
            "target_path_length_m": TRAJECTORY_LENGTH_M,
            "path_length_m": actual_length,
            "max_displacement_from_first_m": max_displacement,
        },
        "sequence": records,
    }
    atomic_json(output_path, payload)
    return payload


def render_command(run_dir: Path, native_blend: Path, gpu: int) -> list[str]:
    return [
        str(BLENDER),
        "-b",
        str(native_blend),
        "--python",
        str(RENDERER),
        "--",
        "--run-dir",
        str(run_dir),
        "--gpu",
        str(gpu),
    ]


def inspect_outputs(destination: Path) -> dict[str, Any]:
    from PIL import Image, ImageStat

    anchors = sorted((destination / "renders/anchors").glob("rgb_*.png"))
    sequence = sorted((destination / "renders/sequence").glob("rgb_*.png"))
    expected_anchors = [f"rgb_{index:03d}.png" for index in range(8)]
    expected_sequence = [f"rgb_{index:03d}.png" for index in range(1, 51)]
    problems = []
    if [path.name for path in anchors] != expected_anchors:
        problems.append("anchor_inventory")
    if [path.name for path in sequence] != expected_sequence:
        problems.append("sequence_inventory")
    image_records = []
    for path, expected_size in [
        *((path, (1280, 720)) for path in anchors),
        *((path, (512, 512)) for path in sequence),
    ]:
        try:
            with Image.open(path) as image:
                image.load()
                extrema = image.convert("RGB").getextrema()
                standard_deviation = ImageStat.Stat(image.convert("RGB")).stddev
                valid = image.size == expected_size and max(standard_deviation) > 1.0
                image_records.append(
                    {
                        "path": str(path.relative_to(destination)),
                        "size": list(image.size),
                        "extrema": extrema,
                        "stddev": standard_deviation,
                        "valid": valid,
                    }
                )
                if not valid:
                    problems.append(f"invalid_image:{path.name}")
        except Exception as error:
            problems.append(f"unreadable_image:{path.name}:{error}")
    camera_path = destination / "renders/sequence/cameras.json"
    try:
        cameras = json.loads(camera_path.read_text(encoding="utf-8"))
        if len(cameras.get("sequence", [])) != FRAME_COUNT:
            problems.append("camera_inventory")
        path_length = float(cameras["path_planner"]["path_length_m"])
        if not 35.0 <= path_length <= 50.0:
            problems.append(f"camera_path_length:{path_length}")
    except Exception as error:
        problems.append(f"invalid_cameras:{error}")
    return {
        "valid": not problems,
        "anchor_count": len(anchors),
        "sequence_count": len(sequence),
        "problems": problems,
        "images": image_records,
    }


def native_complete(case_dir: Path) -> bool:
    required = (
        case_dir / "inputs/layout.png",
        case_dir / "inputs/depth.png",
        case_dir / f"scenes/{STYLE}/city_scene.blend",
        case_dir / f"scenes/{STYLE}/assembly_report.json",
        case_dir / "pipeline_run.json",
    )
    return all(path.is_file() and path.stat().st_size > 0 for path in required)


def execute(args: argparse.Namespace) -> int:
    spec = load_spec(args.spec_id)
    destination, plan_path = prepare_run(args.trial_mode, spec, args.seed)
    case_dir = native_case_dir(args.trial_mode, spec, args.seed)
    manifest_path = destination / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (destination / "SUCCESS").exists() and args.stage == "all":
        print(f"Keeping completed canonical run: {destination}")
        return 0
    command = generation_command(args.trial_mode, spec, args.seed, plan_path)
    if args.stage == "prepare" or args.dry_run:
        command_record = {
            "started_at": utc_now(),
            "command": command,
            "cwd": str(SOURCE_ROOT),
            "proxy_variables_removed": list(PROXY_VARIABLES),
            "dry_run": True,
        }
        atomic_json(destination / "native_command.json", command_record)
        print(json.dumps(command_record, ensure_ascii=False, indent=2))
        return 0

    environment = os.environ.copy()
    for variable in PROXY_VARIABLES:
        environment.pop(variable, None)
    environment.update(
        {
            "PATH": os.pathsep.join(
                (
                    str(BASELINES_ROOT / "envs/majutsucity/bin"),
                    environment.get("PATH", ""),
                )
            ),
            "CUDA_HOME": "/usr/local/cuda-12.4",
            "HF_HOME": os.environ.get(
                "MAJUTSUCITY_HOST_HF_HOME",
                str(BASELINES_ROOT / "cache/huggingface/majutsucity"),
            ),
            "HUGGINGFACE_HUB_CACHE": os.environ.get(
                "MAJUTSUCITY_HOST_HF_HUB_CACHE",
                str(BASELINES_ROOT / "cache/huggingface/majutsucity/hub"),
            ),
            "TORCH_HOME": os.environ.get(
                "MAJUTSUCITY_HOST_TORCH_HOME",
                str(BASELINES_ROOT / "cache/torch/majutsucity"),
            ),
            "XDG_CACHE_HOME": os.environ.get(
                "MAJUTSUCITY_HOST_XDG_CACHE_HOME",
                str(BASELINES_ROOT / "cache/xdg/majutsucity"),
            ),
            "MPLCONFIGDIR": os.environ.get(
                "MAJUTSUCITY_HOST_MPLCONFIGDIR",
                str(BASELINES_ROOT / "cache/matplotlib/majutsucity"),
            ),
            "PYTHONPYCACHEPREFIX": "/tmp/majutsucity_pycache",
            "MAJUTSUCITY_LAYOUT_MIN_FREE_MIB": "47000",
            "MAJUTSUCITY_QWEN_PLACEMENT": "model_cpu_offload",
            "CUDA_VISIBLE_DEVICES": str(args.layout_gpu),
        }
    )
    if args.stage in {"native", "all"}:
        if native_complete(case_dir):
            print(f"Keeping completed native run: {case_dir}")
        else:
            if (
                shutil.disk_usage(BASELINES_ROOT).free
                < args.minimum_free_gib * 1024**3
            ):
                raise RuntimeError(
                    f"Less than {args.minimum_free_gib:g} GiB free below baselines; "
                    "refusing new generation"
                )
            archive_finished_native_attempt(destination)
            command_record = {
                "started_at": utc_now(),
                "command": command,
                "cwd": str(SOURCE_ROOT),
                "proxy_variables_removed": list(PROXY_VARIABLES),
            }
            atomic_json(destination / "native_command.json", command_record)
            log_path = destination / "native_generation.log"
            with log_path.open("a", encoding="utf-8") as log:
                completed = subprocess.run(
                    command,
                    cwd=SOURCE_ROOT,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            command_record["finished_at"] = utc_now()
            command_record["exit_code"] = completed.returncode
            command_record["native_complete"] = native_complete(case_dir)
            atomic_json(destination / "native_command.json", command_record)
            if completed.returncode != 0 or not native_complete(case_dir):
                manifest.update(
                    {
                        "generation_success": False,
                        "render_success": False,
                        "failure_reason": "native_generation_failed",
                    }
                )
                atomic_json(manifest_path, manifest)
                return completed.returncode or 1
        (destination / "NATIVE_SUCCESS").write_text(utc_now() + "\n", encoding="utf-8")
        manifest["generation_success"] = True
        manifest["native_finished_at"] = utc_now()
        atomic_json(manifest_path, manifest)
    if args.stage == "native":
        return 0

    if not native_complete(case_dir):
        raise FileNotFoundError(f"Native MajutsuCity scene is incomplete: {case_dir}")
    layout_path = case_dir / "inputs/layout.png"
    native_blend = case_dir / f"scenes/{STYLE}/city_scene.blend"
    plan_camera_path(layout_path, destination / "input/camera_plan.json")
    scene_dir = destination / "scene"
    scene_dir.mkdir(parents=True, exist_ok=True)
    scene_link = scene_dir / "scene.blend"
    expected_target = os.path.relpath(native_blend, scene_dir)
    if scene_link.is_symlink() and os.readlink(scene_link) != expected_target:
        raise FileExistsError(f"Existing scene link has the wrong target: {scene_link}")
    if not scene_link.exists():
        scene_link.symlink_to(expected_target)
    atomic_json(
        scene_dir / "native_reference.json",
        {
            "native_case_dir": str(case_dir),
            "native_blend": str(native_blend),
            "layout": str(layout_path),
            "assembly_report": str(case_dir / f"scenes/{STYLE}/assembly_report.json"),
        },
    )
    render = render_command(destination, native_blend, args.gpu)
    render_record = {
        "started_at": utc_now(),
        "command": render,
        "physical_gpu": args.gpu,
    }
    atomic_json(destination / "render_command.json", render_record)
    render_environment = environment.copy()
    render_environment["CUDA_VISIBLE_DEVICES"] = str(args.gpu)
    log_path = destination / "render.log"
    with log_path.open("a", encoding="utf-8") as log:
        completed = subprocess.run(
            render,
            cwd=BASELINES_ROOT,
            env=render_environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    validation = inspect_outputs(destination)
    atomic_json(destination / "renders/validation.json", validation)
    render_record.update(
        {
            "finished_at": utc_now(),
            "exit_code": completed.returncode,
            "validation_valid": validation["valid"],
        }
    )
    atomic_json(destination / "render_command.json", render_record)
    success = completed.returncode == 0 and validation["valid"]
    manifest.update(
        {
            "adapter_sha256": sha256_file(Path(__file__)),
            "renderer_sha256": sha256_file(RENDERER),
            "generation_success": True,
            "render_success": success,
            "render_finished_at": utc_now(),
            "failure_reason": None if success else "render_validation_failed",
        }
    )
    atomic_json(manifest_path, manifest)
    if not success:
        return completed.returncode or 1
    (destination / "SUCCESS").write_text(utc_now() + "\n", encoding="utf-8")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec-id", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--trial-mode", choices=("pilot", "formal"), required=True)
    parser.add_argument("--minimum-free-gib", type=float, default=200.0)
    parser.add_argument("--gpu", type=int, default=4)
    parser.add_argument("--layout-gpu", type=int, default=1)
    parser.add_argument(
        "--stage", choices=("prepare", "native", "render", "all"), default="all"
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(execute(parse_args()))
