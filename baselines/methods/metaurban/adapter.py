#!/usr/bin/env python3
"""Deterministic MetaUrban adapter for the urban part of Table 2.

The formal path deliberately refuses MetaUrban's public tiny asset pack.  Tiny
assets are accepted only for explicit smoke tests and their outputs are written
to a separate directory that metric scripts do not scan.
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


import argparse
import hashlib
import json
import math
import os
import platform
import random
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES_ROOT = REPO_ROOT / "baselines"
SOURCE_ROOT = BASELINES_ROOT / "sources/metaurban"
ASSET_ROOT = SOURCE_ROOT / "metaurban/assets"
FULL_ASSET_MANIFEST = (
    BASELINES_ROOT / "methods/metaurban/environment/metaurban_full_assets.json"
)
DEFAULT_SPEC_FILE = BASELINES_ROOT / "protocol/generation/urban_specs.jsonl"
DEFAULT_PROTOCOL = (
    BASELINES_ROOT / "methods/metaurban/protocol/generation/metaurban_protocol.yaml"
)
DEFAULT_DATA_ROOT = BASELINES_ROOT / "data/table2"
SMOKE_DATA_ROOT = BASELINES_ROOT / "data/smoke/metaurban"
PILOT_DATA_ROOT = BASELINES_ROOT / "data/pilot"
SOURCE_COMMIT = "6b8ff9aa48dd27d5c57fa1c712db520732f11fa9"
SOURCE_ARCHIVE_SHA256 = (
    "4933b8ba8614c3a701db1b4ce0ede87dd5cae407fd2ff24842814879e31aaa5a"
)
CAMERA_HEIGHT_M = 1.65
CAMERA_FOV_DEGREES = 70.0
TRAJECTORY_LENGTH_M = 42.0
LOOK_ROTATION_DEGREES = 75.0
FRAME_COUNT = 50
ANCHOR_INDICES = (0, 7, 14, 21, 28, 35, 42, 49)
ALLOWED_GPUS = (0, 1)

CATEGORY_TO_SIDEWALK = {
    "residential": "Neighborhood 1",
    "commercial": "Wide Commercial",
    "mixed_use": "Medium Commercial",
    "park_edge": "Ribbon Sidewalk",
    "leisure_civic": "Neighborhood 2",
}

# MetaUrban has no native offset/irregular intersection primitive.  The fixed
# compound sequences below are declared approximations, never post-selected.
TOPOLOGY_TO_MAP = {
    "four_way": "X",
    "t_junction": "T",
    "main_road_side_road": "T",
    "offset_intersection": "TT",
    "irregular_intersection": "CX",
}


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


def ensure_under_baselines(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(BASELINES_ROOT.resolve())
    except ValueError as error:
        raise ValueError(f"Path must remain below {BASELINES_ROOT}: {path}") from error
    return resolved


def load_specs(path: Path = DEFAULT_SPEC_FILE) -> dict[str, dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            spec = json.loads(line)
            if spec.get("domain") != "urban":
                raise ValueError(f"Non-urban spec at line {line_number}")
            spec_id = str(spec["spec_id"])
            if spec_id in specs:
                raise ValueError(f"Duplicate spec_id={spec_id!r}")
            specs[spec_id] = spec
    return specs


def method_seed(spec: dict[str, Any], logical_seed: int) -> int:
    if logical_seed not in (0, 1, 2, 3):
        raise ValueError("Table-2 logical seed must be one of 0,1,2,3")
    return int(spec["spec_index"]) * 4 + logical_seed


def predefined_config(sidewalk_type: str, native_map: str) -> dict[str, Any]:
    return {
        "Env": "Static",
        "Blocks": [{"Map": native_map}],
        "Sidewalk": [
            {"Type": sidewalk_type},
            {"Buffer_Lane_Furnishing_Width": [0.4, 0.6]},
            {"Furnishing_Width": [1.5, 1.8]},
            {"Clear_Width": [3.0, 3.3]},
            {"Buffer_Frontage_Clear_Width": [0.3, 0.5]},
            {"Frontage_Width": [3.0, 3.3]},
            {"Building_Width": [12.5, 12.5]},
        ],
        "ObjectDensity": 0.6,
        "BackgroundAgent": [
            {"Human_Density": 0.0},
            {"RobotDog_Density": 0.0},
            {"Humanoid_Density": 0.0},
            {"DeliveryRobot_Density": 0.0},
            {"WheelChair_Density": 0.0},
            {"Total_Number": 0},
        ],
        "Rendering": False,
        "ManualControl": False,
        "ObservationType": "rgb",
    }


def build_native_input(spec: dict[str, Any], logical_seed: int) -> dict[str, Any]:
    category = str(spec["category"])
    topology = str(spec["topology"])
    if category not in CATEGORY_TO_SIDEWALK:
        raise ValueError(f"Unsupported urban category: {category}")
    if topology not in TOPOLOGY_TO_MAP:
        raise ValueError(f"Unsupported urban topology: {topology}")
    native_map = TOPOLOGY_TO_MAP[topology]
    exact_topology = topology in {"four_way", "t_junction"}
    return {
        "adapter": "metaurban",
        "adapter_policy": {
            "output_selection": "none",
            "retry_on_quality_failure": False,
            "prompt_tuning_after_output": False,
        },
        "spec_id": spec["spec_id"],
        "logical_seed": logical_seed,
        "method_seed": method_seed(spec, logical_seed),
        "prompt_en_preserved_for_scoring": spec["prompt_en"],
        "native_map": native_map,
        "native_sidewalk_type": CATEGORY_TO_SIDEWALK[category],
        "topology_mapping": "exact" if exact_topology else "fixed_native_approximation",
        "compiled_fields": ["category", "topology"],
        "unsupported_native_fields": [
            "prompt_en",
            "extent_m",
            "required_objects",
            "required_relations",
            "required_facts",
        ],
        "predefined_config": predefined_config(
            CATEGORY_TO_SIDEWALK[category], native_map
        ),
        "frozen_environment": {
            "environment": "SidewalkStaticMetaUrbanEnv",
            "lane_width_m": 3.5,
            "lane_count_per_direction": 3,
            "exit_length_m": 50.0,
            "object_density": 0.6,
            "crosswalk_density": 1.0,
            "traffic_density": 0.0,
            "background_agent_count": 0,
            "static_traffic_object": True,
            "terrain_height_scale": 1.0,
            "render_pipeline": False,
        },
        "camera": {
            "height_m": CAMERA_HEIGHT_M,
            "horizontal_fov_degrees": CAMERA_FOV_DEGREES,
            "trajectory_length_m": TRAJECTORY_LENGTH_M,
            "look_rotation_degrees": LOOK_ROTATION_DEGREES,
            "frames": FRAME_COUNT,
            "anchors_zero_based": list(ANCHOR_INDICES),
            "anchor_resolution": [1280, 720],
            "sequence_resolution": [512, 512],
        },
    }


def asset_inventory() -> dict[str, Any]:
    model_root = ASSET_ROOT / "models/test"
    metadata_root = ASSET_ROOT / "adj_parameter_folder"
    glbs = sorted(model_root.glob("*.glb")) if model_root.exists() else []
    metadata = sorted(metadata_root.glob("*.json")) if metadata_root.exists() else []
    version_path = ASSET_ROOT / "version.txt"
    manifest = None
    if FULL_ASSET_MANIFEST.exists():
        manifest = json.loads(FULL_ASSET_MANIFEST.read_text(encoding="utf-8"))
    return {
        "asset_root": str(ASSET_ROOT),
        "version": version_path.read_text(encoding="utf-8").strip()
        if version_path.exists()
        else None,
        "version_sha256": sha256_file(version_path) if version_path.exists() else None,
        "static_glb_count": len(glbs),
        "metadata_json_count": len(metadata),
        "full_asset_manifest": manifest,
        "full_asset_manifest_sha256": sha256_file(FULL_ASSET_MANIFEST)
        if FULL_ASSET_MANIFEST.exists()
        else None,
    }


def verify_asset_mode(
    trial_mode: str, allow_tiny_assets: bool
) -> tuple[str, dict[str, Any]]:
    inventory = asset_inventory()
    marker = inventory["full_asset_manifest"]
    full_ready = bool(
        marker
        and marker.get("status") == "installed"
        and inventory["static_glb_count"] == marker.get("static_glb_count")
        and inventory["metadata_json_count"] == marker.get("metadata_json_count")
    )
    if full_ready:
        return "full", inventory
    if trial_mode != "smoke" or not allow_tiny_assets:
        raise RuntimeError(
            "Formal/pilot MetaUrban runs require the registered full asset pack. "
            f"Missing valid marker {FULL_ASSET_MANIFEST}; current inventory has "
            f"{inventory['static_glb_count']} GLBs and "
            f"{inventory['metadata_json_count']} metadata files. Tiny assets are "
            "permitted only with --trial-mode smoke --allow-tiny-assets."
        )
    return "tiny", inventory


def intrinsic(width: int, height: int) -> list[list[float]]:
    focal = width / (2.0 * math.tan(math.radians(CAMERA_FOV_DEGREES) / 2.0))
    return [
        [focal, 0.0, width / 2.0],
        [0.0, focal, height / 2.0],
        [0.0, 0.0, 1.0],
    ]


def camera_to_world_opencv(
    position: list[float], view_angle: float
) -> list[list[float]]:
    """Return OpenCV camera axes (right, down, forward) in MetaUrban world."""
    cosine, sine = math.cos(view_angle), math.sin(view_angle)
    return [
        [sine, 0.0, cosine, position[0]],
        [-cosine, 0.0, sine, position[1]],
        [0.0, -1.0, 0.0, position[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def rigid_inverse(matrix: list[list[float]]) -> list[list[float]]:
    rotation = [[matrix[row][column] for column in range(3)] for row in range(3)]
    translation = [matrix[row][3] for row in range(3)]
    inverse_rotation = [list(column) for column in zip(*rotation)]
    inverse_translation = [
        -sum(inverse_rotation[row][column] * translation[column] for column in range(3))
        for row in range(3)
    ]
    return [inverse_rotation[row] + [inverse_translation[row]] for row in range(3)] + [
        [0.0, 0.0, 0.0, 1.0]
    ]


def build_camera_path(lane: Any) -> list[dict[str, Any]]:
    import numpy as np

    lane_length = float(lane.length)
    approach_length = min(32.0, lane_length)
    extension_length = TRAJECTORY_LENGTH_M - approach_length
    start_longitude = lane_length - approach_length
    end_position = np.asarray(lane.position(lane_length, 0.0), dtype=float)
    end_heading = float(lane.heading_theta_at(lane_length))
    end_forward = np.array([math.cos(end_heading), math.sin(end_heading)])
    records: list[dict[str, Any]] = []
    for index in range(FRAME_COUNT):
        alpha = index / (FRAME_COUNT - 1)
        distance = TRAJECTORY_LENGTH_M * alpha
        if distance <= approach_length:
            longitude = start_longitude + distance
            xy = np.asarray(lane.position(longitude, 0.0), dtype=float)
            path_heading = float(lane.heading_theta_at(longitude))
        else:
            overshoot = min(distance - approach_length, extension_length)
            xy = end_position + end_forward * overshoot
            path_heading = end_heading
        view_angle = path_heading + math.radians(LOOK_ROTATION_DEGREES) * alpha
        position = [float(xy[0]), float(xy[1]), CAMERA_HEIGHT_M]
        c2w = camera_to_world_opencv(position, view_angle)
        records.append(
            {
                "frame_index": index,
                "position_m": position,
                "path_heading_degrees": math.degrees(path_heading),
                "view_heading_degrees": math.degrees(view_angle),
                "panda3d_hpr_degrees": [math.degrees(view_angle) - 90.0, 0.0, 0.0],
                "camera_to_world_opencv": c2w,
                "world_to_camera_opencv": rigid_inverse(c2w),
                "K": intrinsic(512, 512),
            }
        )
    return records


def camera_path_stats(records: list[dict[str, Any]]) -> dict[str, float]:
    positions = [record["position_m"] for record in records]
    distance = lambda left, right: math.sqrt(
        sum((a - b) ** 2 for a, b in zip(left, right))
    )
    return {
        "path_length_m": sum(
            distance(left, right) for left, right in zip(positions, positions[1:])
        ),
        "max_displacement_from_first_m": max(
            distance(positions[0], position) for position in positions
        ),
        "look_rotation_degrees": records[-1]["view_heading_degrees"]
        - records[0]["view_heading_degrees"]
        - (records[-1]["path_heading_degrees"] - records[0]["path_heading_degrees"]),
    }


def to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if hasattr(value, "tolist"):
        return to_jsonable(value.tolist())
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def inspect_outputs(run_dir: Path) -> dict[str, Any]:
    from PIL import Image, ImageStat

    anchors = sorted((run_dir / "renders/anchors").glob("rgb_*.png"))
    sequence = sorted((run_dir / "renders/sequence").glob("rgb_*.png"))
    images: list[dict[str, Any]] = []
    image_valid = True
    for path, expected_size in [
        *((path, (1280, 720)) for path in anchors),
        *((path, (512, 512)) for path in sequence),
    ]:
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            stats = ImageStat.Stat(rgb)
            mean = sum(stats.mean) / (3.0 * 255.0)
            std = sum(stats.stddev) / (3.0 * 255.0)
            valid = rgb.size == expected_size and 0.01 <= mean <= 0.99 and std >= 0.01
            image_valid = image_valid and valid
            images.append(
                {
                    "path": str(path.relative_to(run_dir)),
                    "size": list(rgb.size),
                    "mean": mean,
                    "std": std,
                    "valid": valid,
                }
            )
    camera_path = run_dir / "renders/sequence/cameras.json"
    stats = {
        "path_length_m": 0.0,
        "max_displacement_from_first_m": 0.0,
        "look_rotation_degrees": 0.0,
    }
    records: list[dict[str, Any]] = []
    if camera_path.exists():
        records = json.loads(camera_path.read_text(encoding="utf-8")).get(
            "sequence", []
        )
        if records:
            stats = camera_path_stats(records)
    trajectory_valid = (
        len(records) == FRAME_COUNT
        and 35.0 <= stats["path_length_m"] <= 50.0
        and stats["max_displacement_from_first_m"] >= 35.0
        and 60.0 <= stats["look_rotation_degrees"] <= 90.0
        and all(
            abs(record["position_m"][2] - CAMERA_HEIGHT_M) <= 1e-6 for record in records
        )
    )
    valid = (
        len(anchors) == 8
        and len(sequence) == FRAME_COUNT
        and camera_path.exists()
        and image_valid
        and trajectory_valid
        and (run_dir / "scene/scene.json").exists()
    )
    return {
        "valid": valid,
        "anchor_count": len(anchors),
        "sequence_count": len(sequence),
        "image_valid": image_valid,
        "trajectory_valid": trajectory_valid,
        "trajectory": stats,
        "images": images,
    }


def run_dir_for(
    data_root: Path, spec_id: str, logical_seed: int, trial_mode: str
) -> Path:
    if trial_mode == "smoke":
        base = ensure_under_baselines(data_root)
        return base / spec_id / f"seed_{logical_seed}"
    base = ensure_under_baselines(data_root)
    return base / "urban/metaurban" / spec_id / f"seed_{logical_seed}"


def _clear_attempt_outputs(run_dir: Path) -> None:
    ensure_under_baselines(run_dir)
    for relative in ("scene", "renders", "metrics"):
        target = run_dir / relative
        if target.exists():
            shutil.rmtree(target)
    (run_dir / "SUCCESS").unlink(missing_ok=True)


def _map_scene_descriptor(env: Any, native: dict[str, Any]) -> dict[str, Any]:
    scene_map = env.current_map
    blocks = []
    for index, block in enumerate(scene_map.blocks):
        entry: dict[str, Any] = {
            "index": index,
            "id": block.ID,
            "class": type(block).__name__,
            "name": block.name,
        }
        for attribute in ("positive_basic_lane", "negative_basic_lane"):
            lane = getattr(block, attribute, None)
            if lane is not None:
                entry[attribute] = {
                    "start": to_jsonable(lane.position(0.0, 0.0)),
                    "end": to_jsonable(lane.position(float(lane.length), 0.0)),
                    "length_m": float(lane.length),
                }
        blocks.append(entry)
    asset_manager = getattr(env.engine, "asset_manager", None)
    return {
        "representation": "metaurban_procedural_scene_descriptor",
        "regeneration_input": "../input/native_input.json",
        "source_commit": SOURCE_COMMIT,
        "method_seed": native["method_seed"],
        "map_config": to_jsonable(scene_map.config),
        "blocks": blocks,
        "static_object_count": int(getattr(asset_manager, "count", 0)),
    }


def render_run(
    spec: dict[str, Any],
    logical_seed: int,
    gpu: int,
    trial_mode: str,
    allow_tiny_assets: bool,
    data_root: Path,
    force: bool,
) -> bool:
    if gpu not in ALLOWED_GPUS:
        raise ValueError(
            f"MetaUrban may use only physical GPUs {ALLOWED_GPUS}, got {gpu}"
        )
    visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    if visible not in (None, str(gpu)):
        raise RuntimeError(
            f"CUDA_VISIBLE_DEVICES={visible!r} does not match --gpu {gpu}"
        )
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu)
    os.environ.setdefault("METAURBANHOME", str(SOURCE_ROOT))
    os.environ.setdefault("PYTHONPATH", str(SOURCE_ROOT))
    os.environ.setdefault(
        "MPLCONFIGDIR", str(BASELINES_ROOT / "cache/matplotlib/metaurban")
    )
    os.environ.setdefault("XDG_CACHE_HOME", str(BASELINES_ROOT / "cache/xdg/metaurban"))
    # When this file is executed directly, its ``adapters`` directory precedes
    # PYTHONPATH and would otherwise shadow the upstream ``metaurban`` package.
    source_text = str(SOURCE_ROOT)
    if not sys.path or sys.path[0] != source_text:
        sys.path.insert(0, source_text)

    asset_mode, inventory = verify_asset_mode(trial_mode, allow_tiny_assets)
    native = build_native_input(spec, logical_seed)
    if data_root == DEFAULT_DATA_ROOT and trial_mode == "smoke":
        root = SMOKE_DATA_ROOT
    elif data_root == DEFAULT_DATA_ROOT and trial_mode == "pilot":
        root = PILOT_DATA_ROOT
    else:
        root = data_root
    run_dir = run_dir_for(root, spec["spec_id"], logical_seed, trial_mode)
    ensure_under_baselines(run_dir)
    if (run_dir / "SUCCESS").exists() and not force:
        manifest_path = run_dir / "run_manifest.json"
        existing = (
            json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest_path.exists()
            else {}
        )
        expected_asset_mode = "tiny" if trial_mode == "smoke" else "full"
        reusable = (
            existing.get("trial_mode") == trial_mode
            and existing.get("asset_mode") == expected_asset_mode
            and existing.get("adapter_sha256") == sha256_file(Path(__file__))
            and existing.get("protocol_sha256") == sha256_file(DEFAULT_PROTOCOL)
            and existing.get("validation", {}).get("valid") is True
        )
        if reusable:
            print(
                f"SKIP MetaUrban {spec['spec_id']} seed={logical_seed} mode={trial_mode}"
            )
            return True
        print(
            f"RERUN_STALE MetaUrban {spec['spec_id']} seed={logical_seed} "
            f"mode={trial_mode}"
        )
    run_dir.mkdir(parents=True, exist_ok=True)
    _clear_attempt_outputs(run_dir)
    atomic_json(run_dir / "input/spec.json", spec)
    atomic_json(run_dir / "input/native_input.json", native)
    log_path = run_dir / "logs/run.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started_at = utc_now()
    started = time.monotonic()
    success = False
    failure_reason = None
    validation: dict[str, Any] = {"valid": False}
    renderer_info: dict[str, Any] = {}
    env = None
    try:
        import cv2
        import numpy as np
        import torch
        from metaurban.component.sensors.rgb_camera import RGBCamera
        from metaurban.envs import SidewalkStaticMetaUrbanEnv
        from metaurban.envs.base_env import BASE_DEFAULT_CONFIG
        from metaurban.engine.engine_utils import close_engine
        from metaurban.engine.engine_utils import initialize_engine

        random.seed(native["method_seed"])
        np.random.seed(native["method_seed"])
        torch.manual_seed(native["method_seed"])
        torch.cuda.manual_seed_all(native["method_seed"])

        # Required by MetaUrban's documented headless-rendering workaround.
        warmup = BASE_DEFAULT_CONFIG.copy()
        warmup["debug"] = True
        initialize_engine(warmup)
        close_engine()

        env_config = {
            "map": native["native_map"],
            "start_seed": native["method_seed"],
            "num_scenarios": 1,
            "tiny": asset_mode == "tiny",
            "use_render": False,
            "image_observation": True,
            "image_on_cuda": False,
            "camera_fov": CAMERA_FOV_DEGREES,
            "sensors": {
                "rgb_sequence": (RGBCamera, 512, 512),
                "rgb_anchor": (RGBCamera, 1280, 720),
            },
            "vehicle_config": {
                "image_source": "rgb_sequence",
                "show_lidar": False,
                "show_navi_mark": False,
                "show_dest_mark": False,
                "show_line_to_dest": False,
                "show_line_to_navi_mark": False,
            },
            "interface_panel": [],
            "show_interface": False,
            "show_ego_navigation": False,
            "show_coordinates": False,
            "show_sidewalk": True,
            "show_crosswalk": True,
            "height_scale": 1.0,
            "render_pipeline": False,
            "object_density": 0.6,
            "crswalk_density": 1.0,
            "traffic_density": 0.0,
            "spawn_human_num": 0,
            "spawn_wheelchairman_num": 0,
            "spawn_edog_num": 0,
            "spawn_erobot_num": 0,
            "spawn_drobot_num": 0,
            "static_traffic_object": True,
            "accident_prob": 0.0,
            "random_lane_width": False,
            "random_lane_num": False,
            "preload_models": False,
            "force_destroy": True,
            "predefined_config": native["predefined_config"],
        }
        env = SidewalkStaticMetaUrbanEnv(env_config)
        env.reset(seed=native["method_seed"])
        gsg = env.engine.win.getGsg()
        renderer_info = {
            "vendor": gsg.getDriverVendor(),
            "renderer": gsg.getDriverRenderer(),
            "version": gsg.getDriverVersion(),
            "physical_gpu_requested": gpu,
        }
        renderer_text = f"{renderer_info['vendor']} {renderer_info['renderer']}".lower()
        if "nvidia" not in renderer_text or "l40s" not in renderer_text:
            raise RuntimeError(
                f"Expected NVIDIA L40S OpenGL renderer, got {renderer_info}"
            )

        scene_map = env.current_map
        target_block = scene_map.blocks[-1]
        lane = getattr(target_block, "positive_basic_lane", None)
        if lane is None:
            raise RuntimeError("Target block does not expose positive_basic_lane")
        camera_records = build_camera_path(lane)
        stats = camera_path_stats(camera_records)
        if not (35.0 <= stats["path_length_m"] <= 50.0):
            raise RuntimeError(f"Invalid frozen trajectory length: {stats}")

        sequence_dir = run_dir / "renders/sequence"
        anchor_dir = run_dir / "renders/anchors"
        sequence_dir.mkdir(parents=True, exist_ok=True)
        anchor_dir.mkdir(parents=True, exist_ok=True)
        sequence_sensor = env.engine.get_sensor("rgb_sequence")
        anchor_sensor = env.engine.get_sensor("rgb_anchor")
        vertical_fov = math.degrees(
            2.0 * math.atan(math.tan(math.radians(CAMERA_FOV_DEGREES) / 2.0))
        )
        sequence_sensor.get_lens().setFov(CAMERA_FOV_DEGREES, vertical_fov)
        anchor_vertical_fov = math.degrees(
            2.0
            * math.atan(
                math.tan(math.radians(CAMERA_FOV_DEGREES) / 2.0) / (1280.0 / 720.0)
            )
        )
        anchor_sensor.get_lens().setFov(CAMERA_FOV_DEGREES, anchor_vertical_fov)
        anchor_number = 0
        for record in camera_records:
            position = record["position_m"]
            hpr = record["panda3d_hpr_degrees"]
            image = sequence_sensor.perceive(
                to_float=False,
                new_parent_node=env.engine.origin,
                position=position,
                hpr=hpr,
            )
            output = sequence_dir / f"rgb_{record['frame_index']:03d}.png"
            if not cv2.imwrite(str(output), image):
                raise RuntimeError(f"Could not write {output}")
            if record["frame_index"] in ANCHOR_INDICES:
                anchor_image = anchor_sensor.perceive(
                    to_float=False,
                    new_parent_node=env.engine.origin,
                    position=position,
                    hpr=hpr,
                )
                anchor_output = anchor_dir / f"rgb_{anchor_number:03d}.png"
                if not cv2.imwrite(str(anchor_output), anchor_image):
                    raise RuntimeError(f"Could not write {anchor_output}")
                anchor_number += 1
        atomic_json(
            sequence_dir / "cameras.json",
            {
                "coordinate_system": "MetaUrban world + OpenCV camera axes",
                "height_m": CAMERA_HEIGHT_M,
                "horizontal_fov_degrees": CAMERA_FOV_DEGREES,
                "trajectory": stats,
                "anchor_indices_zero_based": list(ANCHOR_INDICES),
                "sequence": camera_records,
            },
        )
        atomic_json(run_dir / "scene/scene.json", _map_scene_descriptor(env, native))
        validation = inspect_outputs(run_dir)
        atomic_json(run_dir / "renders/validation.json", validation)
        success = bool(validation["valid"])
        if not success:
            failure_reason = "output_validation_failed"
    except Exception:
        failure_reason = "generation_or_render_exception"
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        if env is not None:
            env.close()

    manifest = {
        "method": "metaurban",
        "domain": "urban",
        "spec_id": spec["spec_id"],
        "spec_index": spec["spec_index"],
        "logical_seed": logical_seed,
        "method_seed": native["method_seed"],
        "trial_mode": trial_mode,
        "asset_mode": asset_mode,
        "assets": inventory,
        "source_commit": SOURCE_COMMIT,
        "source_archive_sha256": SOURCE_ARCHIVE_SHA256,
        "spec_sha256": sha256_file(DEFAULT_SPEC_FILE),
        "protocol_sha256": sha256_file(DEFAULT_PROTOCOL),
        "adapter_sha256": sha256_file(Path(__file__)),
        "native_input_sha256": sha256_file(run_dir / "input/native_input.json"),
        "hardware": {
            "hostname": platform.node(),
            "physical_gpu_index_requested": gpu,
            "opengl": renderer_info,
        },
        "started_at_utc": started_at,
        "ended_at_utc": utc_now(),
        "wall_time_s": time.monotonic() - started,
        "success": success,
        "generation_success": success,
        "render_success": success,
        "failure_reason": failure_reason,
        "validation": validation,
    }
    atomic_json(run_dir / "run_manifest.json", manifest)
    if success:
        (run_dir / "SUCCESS").touch()
    print(
        f"METAURBAN {'OK' if success else 'FAILED'} mode={trial_mode} "
        f"spec={spec['spec_id']} seed={logical_seed} gpu={gpu} "
        f"asset_mode={asset_mode} wall={manifest['wall_time_s']:.1f}s"
    )
    if failure_reason and log_path.exists():
        print(
            log_path.read_text(encoding="utf-8", errors="replace")[-4000:],
            file=sys.stderr,
        )
    return success


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec-file", type=Path, default=DEFAULT_SPEC_FILE)
    parser.add_argument("--spec-id", required=True)
    parser.add_argument("--seed", type=int, required=True, dest="logical_seed")
    parser.add_argument("--gpu", type=int, choices=ALLOWED_GPUS, default=0)
    parser.add_argument(
        "--trial-mode", choices=("smoke", "pilot", "formal"), default="formal"
    )
    parser.add_argument("--allow-tiny-assets", action="store_true")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.allow_tiny_assets and args.trial_mode != "smoke":
        raise ValueError("--allow-tiny-assets is valid only with --trial-mode smoke")
    specs = load_specs(args.spec_file)
    if args.spec_id not in specs:
        raise KeyError(f"Unknown spec_id={args.spec_id!r}")
    ok = render_run(
        specs[args.spec_id],
        args.logical_seed,
        args.gpu,
        args.trial_mode,
        args.allow_tiny_assets,
        args.data_root,
        args.force,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
