#!/usr/bin/env python3
"""Evaluate WorldGen plus a frozen deterministic indoor/outdoor adapter.

The native WorldGen artifacts are immutable inputs.  This adapter adds a
method-independent canonical shell, shared portal, approach, and navigation
layout so the seven unified-world columns can be measured as a separate system
row.  It never edits or copies the large native geometry files.
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
import base64
import concurrent.futures
import csv
import hashlib
import json
import math
import random
import re
import shutil
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont


REPO = _BASELINE_PROJECT_ROOT
BASELINES = REPO / "baselines"
PACKAGE_ROOT = BASELINES / "methods/worldgen/unified/fixed_adapter"
PROTOCOL_DIR = BASELINES / "methods/worldgen/protocol/unified/fixed_adapter"
PROTOCOL_PATH = PROTOCOL_DIR / "protocol.yaml"
PROMPT_PATH = PROTOCOL_DIR / "spatial_aqs_prompt.txt"
LOCK_PATH = PROTOCOL_DIR / "method.lock.json"
SOURCE_RUNNER = BASELINES / "methods/worldgen/unified/native/worldgen_unified.py"
SOURCE_LOCK = (
    BASELINES / "methods/worldgen/protocol/unified/native/worldgen_method.lock.json"
)
SOURCE_SUMMARY = BASELINES / "results/table4_worldgen/summary.json"
SOURCE_AUDIT = BASELINES / "results/table4_worldgen/audit.json"
MODEL_MANIFEST = BASELINES / "hyworld2_runtime/manifests/qwen3_vl_8b_modelscope.json"
QWEN_ROOT = BASELINES / "hyworld2_runtime/checkpoints/Qwen3-VL-8B-Instruct"
RECAST_RUNTIME = BASELINES / "methods/worldgen/geometry/runtime/recast_glibc231_clean2"
NAVMESH_EVALUATOR = BASELINES / "evaluation/geometry/metrics/build_navmesh.py"
RECAST_BINARY = RECAST_RUNTIME / "recast.cpython-311-x86_64-linux-gnu.so"
BLIND_SALT = "worldbridge-table4-worldgen-fixed-io-adapter-v1"

METRICS = (
    "functional_aqs",
    "visual_aqs",
    "spatial_aqs",
    "shape_iou",
    "entrance_alignment",
    "entrance_passability",
    "transition_collision",
    "io_connectivity_rate",
    "cross_boundary_reachability",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_protocol() -> dict[str, Any]:
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def atomic_json(path: Path, value: Any) -> None:
    atomic_text(
        path, json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(REPO.resolve()))


def require_below_baselines(path: Path) -> Path:
    resolved = path.resolve()
    resolved.relative_to(BASELINES.resolve())
    return resolved


def source_module() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "table4_worldgen_frozen_source", SOURCE_RUNNER
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import source runner: {SOURCE_RUNNER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def trial_paths(trial: str) -> tuple[Path, Path, Path, Path, Path, Path]:
    protocol = load_protocol()
    paths = protocol["paths"]
    if trial == "formal":
        return (
            BASELINES / protocol["source_formal_data"].removeprefix("baselines/"),
            BASELINES
            / protocol["source_formal_annotations"].removeprefix("baselines/"),
            BASELINES / protocol["source_formal_results"].removeprefix("baselines/"),
            BASELINES / paths["formal_data"].removeprefix("baselines/"),
            BASELINES / paths["formal_annotations"].removeprefix("baselines/"),
            BASELINES / paths["formal_results"].removeprefix("baselines/"),
        )
    if trial == "pilot":
        return (
            BASELINES / protocol["source_pilot_data"].removeprefix("baselines/"),
            BASELINES / protocol["source_pilot_annotations"].removeprefix("baselines/"),
            BASELINES / protocol["source_pilot_results"].removeprefix("baselines/"),
            BASELINES / paths["pilot_data"].removeprefix("baselines/"),
            BASELINES / paths["pilot_annotations"].removeprefix("baselines/"),
            BASELINES / paths["pilot_results"].removeprefix("baselines/"),
        )
    raise ValueError(f"Unsupported trial: {trial}")


def specs_and_seeds(trial: str) -> tuple[list[dict[str, Any]], list[int]]:
    source = source_module()
    return source.trial_specs_and_seeds(trial)


def run_dir(root: Path, spec_id: str, seed: int) -> Path:
    if "/" in spec_id or spec_id in {".", ".."}:
        raise ValueError(f"Unsafe spec id: {spec_id}")
    return require_below_baselines(root / spec_id / f"seed_{seed}")


def blind_id(spec_id: str, seed: int) -> str:
    digest = (
        hashlib.sha256(f"{BLIND_SALT}|{spec_id}|{seed}".encode())
        .hexdigest()[:12]
        .upper()
    )
    return f"A-{digest}"


def source_private_map(annotation_root: Path) -> dict[tuple[str, int], dict[str, Any]]:
    payload = json.loads(
        (annotation_root / "PRIVATE_blind_map.json").read_text(encoding="utf-8")
    )
    return {(row["spec_id"], int(row["logical_seed"])): row for row in payload["items"]}


def add_quad(
    vertices: list[list[float]], faces: list[list[int]], points: list[list[float]]
) -> None:
    offset = len(vertices)
    vertices.extend(points)
    faces.extend([[offset, offset + 1, offset + 2], [offset, offset + 2, offset + 3]])


def add_box(
    vertices: list[list[float]],
    faces: list[list[int]],
    bounds: tuple[float, float, float, float, float, float],
) -> None:
    xmin, xmax, ymin, ymax, zmin, zmax = bounds
    offset = len(vertices)
    vertices.extend(
        [
            [xmin, ymin, zmin],
            [xmax, ymin, zmin],
            [xmax, ymax, zmin],
            [xmin, ymax, zmin],
            [xmin, ymin, zmax],
            [xmax, ymin, zmax],
            [xmax, ymax, zmax],
            [xmin, ymax, zmax],
        ]
    )
    faces.extend(
        [
            [offset, offset + 2, offset + 1],
            [offset, offset + 3, offset + 2],
            [offset + 4, offset + 5, offset + 6],
            [offset + 4, offset + 6, offset + 7],
            [offset, offset + 1, offset + 5],
            [offset, offset + 5, offset + 4],
            [offset + 1, offset + 2, offset + 6],
            [offset + 1, offset + 6, offset + 5],
            [offset + 2, offset + 3, offset + 7],
            [offset + 2, offset + 7, offset + 6],
            [offset + 3, offset, offset + 4],
            [offset + 3, offset + 4, offset + 7],
        ]
    )


def canonical_geometry(
    protocol: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    shell = protocol["adapter"]["building_shell"]
    portal = protocol["adapter"]["portal"]
    walkway = protocol["adapter"]["walkway"]
    width = float(shell["footprint_width_m"])
    depth = float(shell["footprint_depth_m"])
    thickness = float(shell["wall_thickness_m"])
    height = float(shell["wall_height_m"])
    inner_x = 0.5 * width - thickness
    inner_front = -0.5 * depth + thickness
    inner_back = 0.5 * depth - thickness
    half_door = 0.5 * float(portal["width_m"])
    vertices: list[list[float]] = []
    faces: list[list[int]] = []
    # Walkable surfaces are separate but exactly touching; Recast performs the
    # common voxelization and is not given an off-mesh link.
    add_quad(
        vertices,
        faces,
        [
            [-inner_x, inner_front, 0],
            [inner_x, inner_front, 0],
            [inner_x, inner_back, 0],
            [-inner_x, inner_back, 0],
        ],
    )
    add_quad(
        vertices,
        faces,
        [
            [-half_door, -0.5 * depth, 0],
            [half_door, -0.5 * depth, 0],
            [half_door, inner_front, 0],
            [-half_door, inner_front, 0],
        ],
    )
    wx0, wx1 = map(float, walkway["x_range_m"])
    wy0, wy1 = map(float, walkway["outside_y_range_m"])
    add_quad(
        vertices, faces, [[wx0, wy0, 0], [wx1, wy0, 0], [wx1, wy1, 0], [wx0, wy1, 0]]
    )
    wall_boxes = [
        {
            "name": "wall_left",
            "bounds": [-0.5 * width, -inner_x, -0.5 * depth, 0.5 * depth, 0.0, height],
        },
        {
            "name": "wall_right",
            "bounds": [inner_x, 0.5 * width, -0.5 * depth, 0.5 * depth, 0.0, height],
        },
        {
            "name": "wall_back",
            "bounds": [-inner_x, inner_x, inner_back, 0.5 * depth, 0.0, height],
        },
        {
            "name": "wall_front_left",
            "bounds": [-inner_x, -half_door, -0.5 * depth, inner_front, 0.0, height],
        },
        {
            "name": "wall_front_right",
            "bounds": [half_door, inner_x, -0.5 * depth, inner_front, 0.0, height],
        },
        {
            "name": "door_lintel",
            "bounds": [
                -half_door,
                half_door,
                -0.5 * depth,
                inner_front,
                float(portal["height_m"]),
                height,
            ],
        },
    ]
    for box in wall_boxes:
        add_box(vertices, faces, tuple(float(value) for value in box["bounds"]))
    return (
        np.asarray(vertices, dtype=np.float32),
        np.asarray(faces, dtype=np.int32),
        wall_boxes,
    )


def rectangle_iou(left: list[list[float]], right: list[list[float]]) -> float:
    lx = [point[0] for point in left]
    ly = [point[1] for point in left]
    rx = [point[0] for point in right]
    ry = [point[1] for point in right]
    intersection = max(0.0, min(max(lx), max(rx)) - max(min(lx), min(rx))) * max(
        0.0, min(max(ly), max(ry)) - max(min(ly), min(ry))
    )
    left_area = (max(lx) - min(lx)) * (max(ly) - min(ly))
    right_area = (max(rx) - min(rx)) * (max(ry) - min(ry))
    union = left_area + right_area - intersection
    return intersection / union if union > 0 else 0.0


def portal_record(protocol: dict[str, Any], side: str) -> dict[str, Any]:
    portal = protocol["adapter"]["portal"]
    return {
        "portal_id": "fixed_shared_portal_0",
        "side": side,
        "center_xyz_m": list(portal["center_xyz_m"]),
        "outward_normal_xyz": list(portal["outward_normal_xyz"]),
        "width_m": float(portal["width_m"]),
        "height_m": float(portal["height_m"]),
        "bottom_z_m": float(portal["bottom_z_m"]),
        "state": portal["state"],
        "source": "measured from the deterministic adapter collision aperture",
    }


def entrance_alignment(
    exterior: dict[str, Any], interior: dict[str, Any], protocol: dict[str, Any]
) -> dict[str, Any]:
    cfg = protocol["metrics"]["entrance_alignment"]
    p0 = np.asarray(exterior["center_xyz_m"], dtype=float)
    p1 = np.asarray(interior["center_xyz_m"], dtype=float)
    normal = np.asarray(exterior["outward_normal_xyz"], dtype=float)
    normal /= np.linalg.norm(normal)
    other = np.asarray(interior["outward_normal_xyz"], dtype=float)
    other /= np.linalg.norm(other)
    delta = p1 - p0
    normal_distance = abs(float(np.dot(delta, normal)))
    tangent_offset = float(np.linalg.norm(delta - np.dot(delta, normal) * normal))
    bottom_delta = abs(float(exterior["bottom_z_m"]) - float(interior["bottom_z_m"]))
    angle = math.degrees(math.acos(float(np.clip(np.dot(normal, other), -1.0, 1.0))))
    intersection = min(float(exterior["width_m"]), float(interior["width_m"])) * min(
        float(exterior["height_m"]), float(interior["height_m"])
    )
    union = (
        float(exterior["width_m"]) * float(exterior["height_m"])
        + float(interior["width_m"]) * float(interior["height_m"])
        - intersection
    )
    aperture_iou = intersection / union
    checks = {
        "normal_distance": normal_distance <= float(cfg["max_normal_distance_m"]),
        "tangent_offset": tangent_offset <= float(cfg["max_tangent_offset_m"]),
        "bottom_delta": bottom_delta <= float(cfg["max_bottom_delta_m"]),
        "normal_angle": angle <= float(cfg["max_normal_angle_deg"]),
        "aperture_iou": aperture_iou >= float(cfg["min_aperture_iou"]),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "normal_distance_m": normal_distance,
        "tangent_offset_m": tangent_offset,
        "bottom_delta_m": bottom_delta,
        "normal_angle_deg": angle,
        "aperture_iou": aperture_iou,
    }


def capsule_collides(
    point_xy: tuple[float, float],
    wall_boxes: list[dict[str, Any]],
    protocol: dict[str, Any],
) -> bool:
    radius = float(protocol["agent"]["radius_m"])
    height = float(protocol["agent"]["height_m"])
    x, y = point_xy
    for item in wall_boxes:
        xmin, xmax, ymin, ymax, zmin, zmax = item["bounds"]
        if zmin >= height or zmax <= 0.0:
            continue
        dx = max(float(xmin) - x, 0.0, x - float(xmax))
        dy = max(float(ymin) - y, 0.0, y - float(ymax))
        if math.hypot(dx, dy) < radius - 1e-9:
            return True
    return False


def transition_collision(
    wall_boxes: list[dict[str, Any]], protocol: dict[str, Any]
) -> dict[str, Any]:
    portal = protocol["adapter"]["portal"]
    center = np.asarray(portal["center_xyz_m"], dtype=float)
    normal = np.asarray(portal["outward_normal_xyz"], dtype=float)
    outside = center + normal * float(
        protocol["metrics"]["entrance_passability"]["outside_probe_m"]
    )
    inside = center - normal * float(
        protocol["metrics"]["entrance_passability"]["inside_probe_m"]
    )
    distance = float(np.linalg.norm(inside[:2] - outside[:2]))
    sample_count = (
        int(
            math.ceil(
                distance
                / float(protocol["metrics"]["transition_collision"]["sample_step_m"])
            )
        )
        + 1
    )
    samples = np.linspace(outside[:2], inside[:2], sample_count)
    blocked = [
        capsule_collides((float(point[0]), float(point[1])), wall_boxes, protocol)
        for point in samples
    ]
    return {
        "outside_probe_xyz_m": [float(outside[0]), float(outside[1]), 0.0],
        "inside_probe_xyz_m": [float(inside[0]), float(inside[1]), 0.0],
        "sample_count": sample_count,
        "blocked_count": sum(blocked),
        "collision_percent": 100.0 * sum(blocked) / sample_count,
        "any_collision": any(blocked),
    }


def mesh_floor_scale(mesh_path: Path, nominal_camera_height: float) -> dict[str, Any]:
    with mesh_path.open("rb") as handle:
        header = b""
        while b"end_header\n" not in header:
            chunk = handle.read(4096)
            if not chunk or len(header) > 65536:
                raise RuntimeError(f"Invalid PLY header: {mesh_path}")
            header += chunk
    header_end = header.index(b"end_header\n") + len(b"end_header\n")
    match = re.search(rb"element vertex (\d+)", header[:header_end])
    if not match:
        raise RuntimeError(f"PLY vertex count missing: {mesh_path}")
    count = int(match.group(1))
    dtype = np.dtype(
        [
            ("x", "<f8"),
            ("y", "<f8"),
            ("z", "<f8"),
            ("r", "u1"),
            ("g", "u1"),
            ("b", "u1"),
        ]
    )
    vertices = np.memmap(
        mesh_path, mode="r", dtype=dtype, offset=header_end, shape=(count,)
    )
    cap_count = max(1, int(math.ceil(count * 0.05)))
    values = np.asarray(vertices[-cap_count:]["y"], dtype=np.float64)
    values = values[np.isfinite(values)]
    floor_native = float(np.median(values))
    mad = float(np.median(np.abs(values - floor_native)))
    if floor_native <= 1e-4 or mad / floor_native > 0.25:
        raise RuntimeError(
            f"Frozen nadir-floor calibration failed for {mesh_path}: median={floor_native}, mad={mad}"
        )
    return {
        "native_floor_y": floor_native,
        "native_floor_mad": mad,
        "native_floor_relative_mad": mad / floor_native,
        "nominal_camera_height_m": nominal_camera_height,
        "meters_per_native_unit": nominal_camera_height / floor_native,
        "floor_sample_count": len(values),
    }


def geojson_polygon(points: list[list[float]]) -> dict[str, Any]:
    closed = [list(point) for point in points] + [list(points[0])]
    return {
        "type": "Feature",
        "properties": {"unit": "meter"},
        "geometry": {"type": "Polygon", "coordinates": [closed]},
    }


def navmesh_module() -> Any:
    sys.path.insert(0, str(RECAST_RUNTIME))
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "table4_fixed_adapter_navmesh", NAVMESH_EVALUATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot import common NavMesh evaluator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save_navmesh(path: Path, vertices: np.ndarray, faces: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        np.savez_compressed(
            handle,
            vertices=np.asarray(vertices, dtype=np.float32),
            faces=np.asarray(faces, dtype=np.int32),
        )


def projection_component(
    point: list[float],
    vertices: np.ndarray,
    faces: np.ndarray,
    components: list[list[int]],
    module: Any,
) -> dict[str, Any]:
    projection = module.spawn_projection(
        tuple(float(value) for value in point), vertices, faces
    )
    component = None
    if projection.get("projected"):
        face_index = int(projection["face_index"])
        component = next(
            (index for index, member in enumerate(components) if face_index in member),
            None,
        )
    projection["component"] = component
    return projection


def make_overlay(
    path: Path, spec: dict[str, Any], blind: str, protocol: dict[str, Any]
) -> None:
    width, height = 2030, 590
    image = Image.new("RGB", (width, height), (244, 246, 249))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    draw.text(
        (30, 20),
        f"ANONYMOUS CANONICAL SPATIAL OVERLAY  {blind}",
        fill=(20, 25, 35),
        font=font,
    )
    draw.text(
        (30, 42),
        "Right-handed Z-up; dimensions in metres; identical rule for every pair",
        fill=(70, 75, 85),
        font=font,
    )
    # Keep the complete -8 m public approach and +5 m back wall visible.
    cx, cy, scale = 1015, 280, 34

    def point(x: float, y: float) -> tuple[int, int]:
        return int(cx + x * scale), int(cy - y * scale)

    outer = [(-6, -5), (6, -5), (6, 5), (-6, 5)]
    inner = [(-5.7, -4.7), (5.7, -4.7), (5.7, 4.7), (-5.7, 4.7)]
    draw.polygon(
        [point(*value) for value in outer],
        fill=(198, 220, 244),
        outline=(36, 91, 156),
        width=4,
    )
    draw.polygon(
        [point(*value) for value in inner],
        fill=(255, 232, 196),
        outline=(211, 120, 28),
        width=4,
    )
    draw.rectangle(
        [point(-1.5, -5), point(1.5, -8)],
        fill=(211, 239, 216),
        outline=(42, 135, 65),
        width=3,
    )
    draw.line([point(-0.6, -4.85), point(0.6, -4.85)], fill=(218, 30, 40), width=8)
    anchors = protocol["adapter"]["anchors"]
    for index, anchor in enumerate(anchors["outdoor"], 1):
        x, y = point(anchor[0], anchor[1])
        draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=(28, 135, 63))
        draw.text((x + 10, y - 7), f"OUT {index}", fill=(20, 80, 35), font=font)
    foyer = anchors["foyer"]
    x, y = point(foyer[0], foyer[1])
    draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=(190, 40, 40))
    draw.text((x + 10, y - 7), "FOYER", fill=(120, 20, 20), font=font)
    goals = spec["indoor_goal_rules"]
    for index, (slot, label) in enumerate(zip(anchors["goal_slots"], goals), 1):
        x, y = point(slot[0], slot[1])
        draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=(116, 65, 169))
        draw.text((x + 10, y - 7), f"G{index}: {label}", fill=(72, 35, 115), font=font)
    draw.text(
        (40, 510),
        "BLUE: exterior footprint  ORANGE: interior shell envelope  RED: shared 1.20 m portal",
        fill=(35, 45, 60),
        font=font,
    )
    draw.text(
        (40, 532),
        f"Function: {spec['function']} | theme: {spec['visual_theme']} | shell: 12.0 m x 10.0 m",
        fill=(35, 45, 60),
        font=font,
    )
    draw.text(
        (40, 554),
        "Canonical collision and registered geometry; source views remain immutable visual inputs.",
        fill=(130, 35, 35),
        font=font,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def build_one(
    source_run: Path,
    output_run: Path,
    spec: dict[str, Any],
    seed: int,
    trial: str,
    protocol: dict[str, Any],
) -> bool:
    source_manifest_path = source_run / "manifest.json"
    if not source_manifest_path.is_file():
        raise FileNotFoundError(source_manifest_path)
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    source_success = (source_run / "SUCCESS").is_file()
    protocol_hash = sha256_file(PROTOCOL_PATH)
    adapter_hash = sha256_file(Path(__file__))
    source_manifest_hash = sha256_file(source_manifest_path)
    input_payload = {
        "method": protocol["method"],
        "display_name": protocol["display_name"],
        "track": protocol["track"],
        "spec_id": spec["spec_id"],
        "logical_seed": seed,
        "source_pair_manifest": rel(source_manifest_path),
        "source_pair_manifest_sha256": source_manifest_hash,
        "protocol_sha256": protocol_hash,
        "adapter_sha256": adapter_hash,
        "human_postprocessing": False,
        "adapter_rule": protocol["adapter"],
    }
    atomic_json(output_run / "input/pair_spec.json", spec)
    atomic_json(output_run / "input/adapter_input.json", input_payload)
    required = [
        output_run / "canonical/collision.ply",
        output_run / "canonical/collision.glb",
        output_run / "canonical/scene.glb",
        output_run / "canonical/frame.json",
        output_run / "canonical/exterior_footprint.geojson",
        output_run / "canonical/interior_envelope.geojson",
        output_run / "canonical/portals.json",
        output_run / "canonical/instances.json",
        output_run / "navigation/navmesh.bin",
        output_run / "navigation/anchors.json",
        output_run / "navigation/components.json",
        output_run / "metrics/per_run.json",
    ]
    if (
        source_success
        and (output_run / "SUCCESS").is_file()
        and all(path.is_file() for path in required)
    ):
        existing = json.loads(
            (output_run / "manifest.json").read_text(encoding="utf-8")
        )
        if (
            existing.get("protocol_sha256") == protocol_hash
            and existing.get("adapter_sha256") == adapter_hash
            and existing.get("source_pair_manifest_sha256") == source_manifest_hash
        ):
            return True
        (output_run / "SUCCESS").unlink(missing_ok=True)
    if not source_success:
        (output_run / "SUCCESS").unlink(missing_ok=True)
        atomic_json(
            output_run / "manifest.json",
            {
                "method": protocol["method"],
                "display_name": protocol["display_name"],
                "track": protocol["track"],
                "trial": trial,
                "spec_id": spec["spec_id"],
                "logical_seed": seed,
                "source_pair_success": False,
                "system_success": False,
                "failure_reason": "source_worldgen_pair_failure",
                "source_pair_manifest": rel(source_manifest_path),
                "source_pair_manifest_sha256": source_manifest_hash,
                "protocol_sha256": protocol_hash,
                "adapter_sha256": adapter_hash,
                "human_postprocessing": False,
                "updated_at_utc": utc_now(),
            },
        )
        return False

    output_run.mkdir(parents=True, exist_ok=True)
    vertices, faces, wall_boxes = canonical_geometry(protocol)
    nav = navmesh_module()
    collision_ply = output_run / "canonical/collision.ply"
    nav.write_ply(collision_ply, vertices, faces)
    import trimesh

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    mesh.export(output_run / "canonical/collision.glb")
    shutil.copyfile(
        output_run / "canonical/collision.glb", output_run / "canonical/scene.glb"
    )
    shell = protocol["adapter"]["building_shell"]
    width, depth = float(shell["footprint_width_m"]), float(shell["footprint_depth_m"])
    footprint = [
        [-width / 2, -depth / 2],
        [width / 2, -depth / 2],
        [width / 2, depth / 2],
        [-width / 2, depth / 2],
    ]
    envelope = [list(value) for value in footprint]
    atomic_json(
        output_run / "canonical/exterior_footprint.geojson", geojson_polygon(footprint)
    )
    atomic_json(
        output_run / "canonical/interior_envelope.geojson", geojson_polygon(envelope)
    )
    exterior_portal = portal_record(protocol, "exterior")
    interior_portal = portal_record(protocol, "interior")
    atomic_json(
        output_run / "canonical/portals.json",
        {"portals": [exterior_portal, interior_portal]},
    )
    atomic_json(
        output_run / "canonical/instances.json",
        {
            "coordinate_system": protocol["adapter"]["coordinate_system"],
            "unit": "meter",
            "instances": [
                {
                    "id": "fixed_building_shell",
                    "role": "target_building+interior_shell",
                    "source": "adapter",
                },
                {
                    "id": "fixed_shared_portal_0",
                    "role": "open_portal",
                    "source": "adapter",
                },
                {
                    "id": "fixed_public_walkway",
                    "role": "public_outdoor",
                    "source": "adapter",
                },
            ],
            "native_geometry_used_for_visual_identity_only": True,
        },
    )
    native_refs: dict[str, Any] = {}
    transform_cfg = protocol["adapter"]["native_visual_transforms"]
    for side in ("exterior", "interior"):
        native_mesh = source_run / "native" / side / "scene/mesh.ply"
        scale = mesh_floor_scale(
            native_mesh, float(transform_cfg["nominal_camera_height_m"][side])
        )
        native_refs[side] = {
            "path": rel(native_mesh),
            "sha256": sha256_file(native_mesh),
            "immutable": True,
            "transform": {
                "axis_mapping": transform_cfg["axis_mapping"],
                "scale_calibration": scale,
                "camera_translation_m": transform_cfg["camera_translation_m"][side],
                "rotation_degrees": 0.0,
            },
        }
    atomic_json(output_run / "canonical/native_geometry_refs.json", native_refs)
    atomic_json(
        output_run / "canonical/frame.json",
        {
            "coordinate_system": protocol["adapter"]["coordinate_system"],
            "unit": "meter",
            "floor_z_m": 0.0,
            "native_visual_transforms": native_refs,
            "collision_geometry": "adapter-generated fixed shell; native panorama meshes preserved but excluded from synthetic collision",
        },
    )
    recast_cfg = {
        key: protocol[key]
        for key in ("agent", "recast", "postprocess", "spawn", "success")
    }
    nav_vertices, nav_faces, nav_meta = nav.build(collision_ply, recast_cfg, 0.0)
    if not nav_meta.get("builder_returned") or len(nav_faces) == 0:
        raise RuntimeError(f"Recast returned no NavMesh for {output_run}")
    save_navmesh(output_run / "navigation/navmesh.bin", nav_vertices, nav_faces)
    components, component_areas = nav.connected_components(nav_vertices, nav_faces)
    anchors_cfg = protocol["adapter"]["anchors"]
    outdoor = [
        projection_component(point, nav_vertices, nav_faces, components, nav)
        for point in anchors_cfg["outdoor"]
    ]
    foyer = projection_component(
        anchors_cfg["foyer"], nav_vertices, nav_faces, components, nav
    )
    goal_labels = list(spec["indoor_goal_rules"])
    goals = [
        {
            "label": label,
            **projection_component(slot, nav_vertices, nav_faces, components, nav),
        }
        for label, slot in zip(goal_labels, anchors_cfg["goal_slots"])
    ]
    atomic_json(
        output_run / "navigation/anchors.json",
        {"outdoor": outdoor, "foyer": foyer, "indoor_goals": goals},
    )
    atomic_json(
        output_run / "navigation/components.json",
        {
            "component_count": len(components),
            "component_areas_m2": component_areas,
            "components": components,
            "recast": nav_meta,
        },
    )
    align = entrance_alignment(exterior_portal, interior_portal, protocol)
    collision = transition_collision(wall_boxes, protocol)
    projected_outdoor = [
        row
        for row in outdoor
        if row.get("projected") and row.get("component") is not None
    ]
    foyer_component = foyer.get("component") if foyer.get("projected") else None
    connected = foyer_component is not None and any(
        row["component"] == foyer_component for row in projected_outdoor
    )
    outside_probe = projection_component(
        collision["outside_probe_xyz_m"], nav_vertices, nav_faces, components, nav
    )
    inside_probe = projection_component(
        collision["inside_probe_xyz_m"], nav_vertices, nav_faces, components, nav
    )
    passable = bool(
        align["passed"]
        and not collision["any_collision"]
        and outside_probe.get("projected")
        and inside_probe.get("projected")
        and outside_probe.get("component") == inside_probe.get("component")
    )
    reach_checks = []
    for outside_index, outside in enumerate(outdoor):
        for goal_index, goal in enumerate(goals):
            reachable = bool(
                outside.get("projected")
                and goal.get("projected")
                and outside.get("component") is not None
                and outside.get("component") == goal.get("component")
            )
            reach_checks.append(
                {
                    "outdoor_index": outside_index,
                    "goal_index": goal_index,
                    "reachable": reachable,
                }
            )
    reach = 100.0 * sum(row["reachable"] for row in reach_checks) / len(reach_checks)
    metrics = {
        "shape_iou": rectangle_iou(footprint, envelope),
        "entrance_alignment": 100.0 if align["passed"] else 0.0,
        "entrance_passability": 100.0 if passable else 0.0,
        "transition_collision": collision["collision_percent"],
        "io_connectivity_rate": 100.0 if connected else 0.0,
        "cross_boundary_reachability": reach,
        "debug": {
            "alignment": align,
            "collision": collision,
            "outside_probe": outside_probe,
            "inside_probe": inside_probe,
            "reach_checks": reach_checks,
            "wall_boxes": wall_boxes,
        },
    }
    atomic_json(output_run / "metrics/per_run.json", metrics)
    make_overlay(
        output_run / "renders/spatial_overlay.png",
        spec,
        blind_id(spec["spec_id"], seed),
        protocol,
    )
    outputs = [
        *required,
        output_run / "canonical/native_geometry_refs.json",
        output_run / "renders/spatial_overlay.png",
    ]
    hashes = {rel(path): sha256_file(path) for path in outputs if path.is_file()}
    manifest = {
        "method": protocol["method"],
        "display_name": protocol["display_name"],
        "track": protocol["track"],
        "trial": trial,
        "spec_id": spec["spec_id"],
        "logical_seed": seed,
        "source_pair_success": True,
        "system_success": True,
        "source_pair_manifest": rel(source_manifest_path),
        "source_pair_manifest_sha256": source_manifest_hash,
        "protocol_sha256": protocol_hash,
        "adapter_sha256": adapter_hash,
        "human_postprocessing": False,
        "native_geometry_policy": protocol["adapter"]["native_geometry_policy"],
        "outputs_sha256": hashes,
        "updated_at_utc": utc_now(),
    }
    atomic_json(output_run / "manifest.json", manifest)
    atomic_text(
        output_run / "SUCCESS",
        "WorldGen plus fixed IO adapter output contract complete\n",
    )
    return True


def verify_lock() -> None:
    if not LOCK_PATH.is_file():
        raise RuntimeError(
            "Formal adapter lock is missing; complete and freeze the pilot first"
        )
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    paths = lock["files"]
    mismatches = []
    for relative, expected in paths.items():
        path = REPO / relative
        actual = sha256_file(path) if path.is_file() else None
        if actual != expected:
            mismatches.append(
                {"path": relative, "expected": expected, "actual": actual}
            )
    if mismatches:
        raise RuntimeError(f"Formal adapter lock mismatch: {mismatches}")


def build_trial(trial: str) -> dict[str, Any]:
    if trial == "formal":
        verify_lock()
    source_data, _, _, output_data, _, _ = trial_paths(trial)
    specs, seeds = specs_and_seeds(trial)
    protocol = load_protocol()
    successes = 0
    for spec in specs:
        for seed in seeds:
            source_run = run_dir(source_data, spec["spec_id"], seed)
            output_run = run_dir(output_data, spec["spec_id"], seed)
            successes += int(
                build_one(source_run, output_run, spec, seed, trial, protocol)
            )
            print(
                f"TABLE4_IO_ADAPTER_BUILD spec={spec['spec_id']} seed={seed} success={(output_run / 'SUCCESS').is_file()}",
                flush=True,
            )
    result = {
        "trial": trial,
        "planned_pairs": len(specs) * len(seeds),
        "successful_pairs": successes,
        "output_root": rel(output_data),
    }
    print(
        f"TABLE4_IO_ADAPTER_BUILD_COMPLETE {json.dumps(result, sort_keys=True)}",
        flush=True,
    )
    return result


def make_spatial_package(trial: str) -> dict[str, Any]:
    source_data, source_annotations, _, output_data, annotation_root, _ = trial_paths(
        trial
    )
    specs, seeds = specs_and_seeds(trial)
    source_map = source_private_map(source_annotations)
    items: list[dict[str, Any]] = []
    private: list[dict[str, Any]] = []
    for spec in specs:
        for seed in seeds:
            output_run = run_dir(output_data, spec["spec_id"], seed)
            success = (output_run / "SUCCESS").is_file()
            anonymous = blind_id(spec["spec_id"], seed)
            private.append(
                {
                    "blind_id": anonymous,
                    "spec_id": spec["spec_id"],
                    "logical_seed": seed,
                    "success": success,
                    "method": "worldgen_fixed_io_adapter",
                    "run_dir": rel(output_run),
                }
            )
            if not success:
                continue
            source_entry = source_map[(spec["spec_id"], seed)]
            source_montage = (
                source_annotations / "montages" / f"{source_entry['blind_id']}.jpg"
            )
            overlay = output_run / "renders/spatial_overlay.png"
            with Image.open(source_montage) as upper_handle, Image.open(
                overlay
            ) as lower_handle:
                upper = upper_handle.convert("RGB")
                # Replace the source-track blind ID with the adapter-track ID so
                # the scorer sees one stable anonymous identity.
                title_draw = ImageDraw.Draw(upper)
                title_draw.rectangle((0, 0, upper.width, 48), fill=(255, 255, 255))
                try:
                    title_font = ImageFont.truetype(
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 21
                    )
                except OSError:
                    title_font = ImageFont.load_default()
                title_draw.text(
                    (15, 12),
                    f"Anonymous indoor-outdoor system {anonymous}",
                    fill=(15, 15, 15),
                    font=title_font,
                )
                lower = lower_handle.convert("RGB")
                if lower.width != upper.width:
                    lower = lower.resize(
                        (upper.width, round(lower.height * upper.width / lower.width)),
                        Image.Resampling.LANCZOS,
                    )
                canvas = Image.new(
                    "RGB", (upper.width, upper.height + lower.height), (245, 245, 245)
                )
                canvas.paste(upper, (0, 0))
                canvas.paste(lower, (0, upper.height))
            montage = annotation_root / "montages" / f"{anonymous}.jpg"
            montage.parent.mkdir(parents=True, exist_ok=True)
            canvas.save(montage, quality=94, subsampling=0)
            items.append(
                {
                    "blind_id": anonymous,
                    "function": spec["function"],
                    "visual_theme": spec["visual_theme"],
                    "target_building": spec["target_building"],
                    "interior_program": spec["interior_program"],
                    "indoor_goal_rules": spec["indoor_goal_rules"],
                    "montage": f"montages/{anonymous}.jpg",
                    "montage_sha256": sha256_file(montage),
                }
            )
    atomic_json(
        annotation_root / "PRIVATE_blind_map.json",
        {"warning": "Do not expose this mapping to a scorer.", "items": private},
    )
    atomic_text(
        annotation_root / "items.jsonl",
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in items
        ),
    )
    manifest = {
        "created_at_utc": utc_now(),
        "trial": trial,
        "planned_pairs": len(private),
        "successful_pairs": len(items),
        "failed_pairs": len(private) - len(items),
        "method_blinded": True,
        "dimensions": ["spatial_aqs"],
        "items_sha256": sha256_file(annotation_root / "items.jsonl"),
        "private_map_sha256": sha256_file(annotation_root / "PRIVATE_blind_map.json"),
    }
    atomic_json(annotation_root / "package_manifest.json", manifest)
    print(
        f"TABLE4_IO_ADAPTER_PACKAGE_COMPLETE {json.dumps(manifest, sort_keys=True)}",
        flush=True,
    )
    return manifest


def spatial_prompt(item: dict[str, Any]) -> str:
    base = PROMPT_PATH.read_text(encoding="utf-8")
    specification = {
        "function": item["function"],
        "visual_theme": item["visual_theme"],
        "target_building": item["target_building"],
        "interior_program": item["interior_program"],
        "registered_indoor_goals": item["indoor_goal_rules"],
    }
    return (
        base
        + "\nFrozen anonymous specification:\n"
        + json.dumps(specification, ensure_ascii=False)
    )


def request_json(port: int, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        request, timeout=600
    ) as response:
        return json.load(response)


def parse_spatial(raw: dict[str, Any]) -> dict[str, Any]:
    content = raw["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise ValueError("VLM response content is not text")
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    parsed = json.loads(text)
    if set(parsed) != {"spatial_aqs", "spatial_evidence"}:
        raise ValueError(f"Unexpected spatial AQS keys: {sorted(parsed)}")
    if type(parsed["spatial_aqs"]) is not int or not 1 <= parsed["spatial_aqs"] <= 10:
        raise ValueError("spatial_aqs must be an integer 1..10")
    if (
        not isinstance(parsed["spatial_evidence"], str)
        or not parsed["spatial_evidence"].strip()
    ):
        raise ValueError("spatial_evidence must be non-empty")
    return parsed


def score_spatial_package(
    trial: str, port: int, request_workers: int
) -> dict[str, Any]:
    _, _, _, _, annotation_root, _ = trial_paths(trial)
    protocol = load_protocol()
    items = [
        json.loads(line)
        for line in (annotation_root / "items.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    model_hash = sha256_file(MODEL_MANIFEST)
    cfg = protocol["spatial_aqs"]

    def score_one(item: dict[str, Any]) -> int:
        image_path = annotation_root / item["montage"]
        image_bytes = image_path.read_bytes()
        if hashlib.sha256(image_bytes).hexdigest() != item["montage_sha256"]:
            raise RuntimeError(f"Changed spatial montage: {image_path}")
        prompt = spatial_prompt(item)
        image_content = {
            "type": "image_url",
            "image_url": {
                "url": "data:image/jpeg;base64,"
                + base64.b64encode(image_bytes).decode()
            },
        }
        for pass_index, seed in enumerate(cfg["seeds"], 1):
            settings = {
                "model": cfg["model"],
                "temperature": cfg["temperature"],
                "top_p": cfg["top_p"],
                "seed": seed,
                "max_tokens": 768,
                "response_format": {"type": "json_object"},
            }
            signature = hashlib.sha256(
                json.dumps(
                    {
                        "settings": settings,
                        "prompt": prompt,
                        "image_sha256": item["montage_sha256"],
                        "model_manifest_sha256": model_hash,
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            output = (
                annotation_root
                / "spatial_aqs_raw"
                / item["blind_id"]
                / f"pass_{pass_index:02d}.json"
            )
            if output.is_file():
                cached = json.loads(output.read_text(encoding="utf-8"))
                if cached.get("input_signature") != signature:
                    raise RuntimeError(
                        f"Refusing changed cached spatial input: {output}"
                    )
                parse_spatial(cached["raw_response"])
                continue
            last_error: Exception | None = None
            for attempt in range(1, 4):
                try:
                    raw = request_json(
                        port,
                        {
                            **settings,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": prompt},
                                        image_content,
                                    ],
                                }
                            ],
                        },
                    )
                    parsed = parse_spatial(raw)
                    atomic_json(
                        output,
                        {
                            "rating_source": "spatial_aqs_vlm_qwen3_vl_8b_three_pass",
                            "human_raters": 0,
                            "pass_index": pass_index,
                            "seed": seed,
                            "input_signature": signature,
                            "image_sha256": item["montage_sha256"],
                            "model_manifest_sha256": model_hash,
                            "settings": settings,
                            "prompt": prompt,
                            "parsed": parsed,
                            "raw_response": raw,
                            "created_at_utc": utc_now(),
                        },
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    print(
                        f"TABLE4_IO_ADAPTER_SPATIAL_RETRY item={item['blind_id']} pass={pass_index} attempt={attempt}/3 error={exc!r}",
                        flush=True,
                    )
            else:
                raise RuntimeError(
                    f"Spatial AQS failed: item={item['blind_id']} pass={pass_index} error={last_error!r}"
                )
        print(f"TABLE4_IO_ADAPTER_SPATIAL_COMPLETE item={item['blind_id']}", flush=True)
        return 1

    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=request_workers) as executor:
        for value in executor.map(
            score_one, sorted(items, key=lambda row: row["blind_id"])
        ):
            completed += value
    provenance = {
        "scored_at_utc": utc_now(),
        "trial": trial,
        "rating_source": "spatial_aqs_vlm_qwen3_vl_8b_three_pass",
        "human_raters": 0,
        "model": cfg["model"],
        "model_manifest_sha256": model_hash,
        "passes_per_pair": len(cfg["seeds"]),
        "seeds": cfg["seeds"],
        "scored_successful_pairs": completed,
        "functional_visual_scores_reused_from": rel(
            SOURCE_SUMMARY
            if trial == "formal"
            else trial_paths(trial)[2] / "summary.json"
        ),
        "limitations": "Spatial AQS judges the complete synthetic-adapter system; it is not native WorldGen spatial ability.",
    }
    atomic_json(annotation_root / "SPATIAL_AQS_VLM_PROVENANCE.json", provenance)
    return provenance


def start_and_score(
    trial: str, gpu: int, port: int, workers: int, external_vllm: bool
) -> dict[str, Any]:
    source = source_module()
    sys.path.insert(0, str(BASELINES))
    import baselines.methods.hyworld.run as matrix

    matrix.QWEN_ROOT = QWEN_ROOT
    matrix.BASELINES_ROOT = BASELINES / ".w"
    process = None
    try:
        if external_vllm:
            if not matrix.llm_health(port):
                raise RuntimeError(f"No healthy local VLM at port {port}")
        else:
            state = source.gpu_state().get(gpu)
            if state is None or state["free_mib"] < 30000 or state["utilization"] > 10:
                raise RuntimeError(f"VLM GPU {gpu} is not idle enough: {state}")
            process, _ = matrix.start_vllm(gpu, port, 16384, 900)
        return score_spatial_package(trial, port, workers)
    finally:
        if process is not None:
            matrix.stop_process_group(process)


def wait_and_score(
    trial: str,
    candidate_gpus: list[int],
    port: int,
    workers: int,
    poll_seconds: int,
    stable_samples: int,
) -> dict[str, Any]:
    if poll_seconds < 10 or stable_samples < 1:
        raise ValueError(
            "poll_seconds must be >=10 and stable_samples must be positive"
        )
    source = source_module()
    stable = {gpu: 0 for gpu in candidate_gpus}
    while True:
        try:
            states = source.gpu_state()
        except Exception as exc:
            print(f"TABLE4_IO_ADAPTER_GPU_WAIT query_error={exc!r}", flush=True)
            time.sleep(poll_seconds)
            continue
        for gpu in candidate_gpus:
            state = states.get(gpu)
            eligible = bool(
                state and state["free_mib"] >= 30000 and state["utilization"] <= 10
            )
            stable[gpu] = stable[gpu] + 1 if eligible else 0
        print(
            f"TABLE4_IO_ADAPTER_GPU_WAIT states={json.dumps(states, sort_keys=True)} stable={json.dumps(stable, sort_keys=True)}",
            flush=True,
        )
        ready = [gpu for gpu in candidate_gpus if stable[gpu] >= stable_samples]
        if ready:
            return start_and_score(trial, ready[0], port, workers, False)
        time.sleep(poll_seconds)


def mean(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        raise ValueError("Cannot average an empty sequence")
    return sum(values) / len(values)


def macro_average(rows: list[dict[str, Any]], metric: str) -> float:
    by_spec: dict[str, list[float]] = {}
    for row in rows:
        by_spec.setdefault(row["spec_id"], []).append(float(row[metric]))
    return mean(mean(values) for values in by_spec.values())


def cluster_bootstrap(
    rows: list[dict[str, Any]], metric: str, repeats: int, seed: int
) -> tuple[float, float]:
    by_spec: dict[str, list[float]] = {}
    for row in rows:
        by_spec.setdefault(row["spec_id"], []).append(float(row[metric]))
    values = [mean(by_spec[key]) for key in sorted(by_spec)]
    generator = random.Random(seed)
    draws = [
        mean(values[generator.randrange(len(values))] for _ in values)
        for _ in range(repeats)
    ]
    return float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))


def aggregate(trial: str) -> dict[str, Any]:
    if trial == "formal":
        verify_lock()
    _, _, source_results, output_data, annotation_root, results_root = trial_paths(
        trial
    )
    specs, seeds = specs_and_seeds(trial)
    protocol = load_protocol()
    source_rows = {
        (row["spec_id"], int(row["logical_seed"])): row
        for row in (
            json.loads(line)
            for line in (source_results / "per_run.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        )
    }
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for spec in specs:
        for seed in seeds:
            output_run = run_dir(output_data, spec["spec_id"], seed)
            success = (output_run / "SUCCESS").is_file()
            if success:
                source_row = source_rows[(spec["spec_id"], seed)]
                geometric = json.loads(
                    (output_run / "metrics/per_run.json").read_text(encoding="utf-8")
                )
                spatial_passes = []
                anonymous = blind_id(spec["spec_id"], seed)
                for pass_index in range(1, int(protocol["spatial_aqs"]["passes"]) + 1):
                    record = json.loads(
                        (
                            annotation_root
                            / "spatial_aqs_raw"
                            / anonymous
                            / f"pass_{pass_index:02d}.json"
                        ).read_text(encoding="utf-8")
                    )
                    spatial_passes.append(
                        parse_spatial(record["raw_response"])["spatial_aqs"]
                    )
                values = {
                    "functional_aqs": float(source_row["functional_aqs"]),
                    "visual_aqs": float(source_row["visual_aqs"]),
                    "spatial_aqs": mean(spatial_passes),
                    **{key: float(geometric[key]) for key in METRICS[3:]},
                }
                failure_reason = None
            else:
                values = {
                    key: float(protocol["failure_values"][key]) for key in METRICS
                }
                failure_reason = "source_worldgen_pair_failure"
                failures.append(
                    {
                        "spec_id": spec["spec_id"],
                        "logical_seed": seed,
                        "reason": failure_reason,
                    }
                )
            rows.append(
                {
                    "method": protocol["method"],
                    "display_name": protocol["display_name"],
                    "track": protocol["track"],
                    "spec_id": spec["spec_id"],
                    "spec_index": spec["spec_index"],
                    "function": spec["function"],
                    "visual_theme": spec["visual_theme"],
                    "logical_seed": seed,
                    "system_success": success,
                    **values,
                    "failure_reason": failure_reason,
                    "functional_visual_rating_source": "reused_frozen_worldgen_aqs"
                    if success
                    else "itt_failure_value",
                    "spatial_rating_source": "spatial_aqs_vlm_qwen3_vl_8b_three_pass"
                    if success
                    else "itt_failure_value",
                    "human_raters": 0,
                }
            )
    repeats = int(protocol["aggregation"]["bootstrap_repeats"])
    bootstrap_seed = int(protocol["aggregation"]["bootstrap_seed"])
    successful_rows = [row for row in rows if row["system_success"]]
    metrics = {
        metric: {
            "mean": macro_average(rows, metric),
            "ci95": list(cluster_bootstrap(rows, metric, repeats, bootstrap_seed)),
            "coverage": 1.0,
            "conditional_success_mean": mean(
                float(row[metric]) for row in successful_rows
            ),
        }
        for metric in METRICS
    }
    summary = {
        "aggregated_at_utc": utc_now(),
        "trial": trial,
        "method": protocol["method"],
        "display_name": protocol["display_name"],
        "track": protocol["track"],
        "planned_pairs": len(rows),
        "successful_pairs": len(successful_rows),
        "success_rate": len(successful_rows) / len(rows),
        "aggregation_order": protocol["aggregation"]["order"],
        "bootstrap_repeats": repeats,
        "bootstrap_seed": bootstrap_seed,
        "metrics": metrics,
        "aqs_source": "Functional/Visual reused from frozen WorldGen Qwen3-VL evaluation; Spatial newly evaluated with Qwen3-VL in three seeded passes; human_raters=0",
        "adapter_attribution": "Shape/portal/navigation results belong to the deterministic adapter system, not native WorldGen.",
    }
    results_root.mkdir(parents=True, exist_ok=True)
    atomic_text(
        results_root / "per_run.jsonl",
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
        ),
    )
    atomic_json(results_root / "summary.json", summary)
    with (results_root / "summary.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        fields = [
            "method",
            "track",
            *METRICS,
            "planned_pairs",
            "successful_pairs",
            "success_rate",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "method": protocol["display_name"],
                "track": protocol["track"],
                **{
                    metric: (
                        f"{metrics[metric]['mean']:.3f}"
                        if metric == "shape_iou"
                        else f"{metrics[metric]['mean']:.2f}"
                        if metric.endswith("aqs")
                        else f"{metrics[metric]['mean']:.1f}"
                    )
                    for metric in METRICS
                },
                "planned_pairs": len(rows),
                "successful_pairs": len(successful_rows),
                "success_rate": f"{len(successful_rows) / len(rows):.6f}",
            }
        )
    with (results_root / "failures.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["spec_id", "logical_seed", "reason"]
        )
        writer.writeheader()
        writer.writerows(failures)
    print(
        f"TABLE4_IO_ADAPTER_AGGREGATE_COMPLETE {json.dumps(summary, sort_keys=True)}",
        flush=True,
    )
    return summary


def audit(trial: str) -> dict[str, Any]:
    if trial == "formal":
        verify_lock()
    (
        source_data,
        _,
        source_results,
        output_data,
        annotation_root,
        results_root,
    ) = trial_paths(trial)
    specs, seeds = specs_and_seeds(trial)
    issues: list[str] = []
    success_count = 0
    source_success_count = 0
    manifest_count = 0
    required_success_files = [
        "canonical/collision.ply",
        "canonical/collision.glb",
        "canonical/scene.glb",
        "canonical/frame.json",
        "canonical/exterior_footprint.geojson",
        "canonical/interior_envelope.geojson",
        "canonical/portals.json",
        "canonical/instances.json",
        "canonical/native_geometry_refs.json",
        "navigation/navmesh.bin",
        "navigation/anchors.json",
        "navigation/components.json",
        "metrics/per_run.json",
        "renders/spatial_overlay.png",
        "SUCCESS",
    ]
    for spec in specs:
        for seed in seeds:
            source_run = run_dir(source_data, spec["spec_id"], seed)
            output_run = run_dir(output_data, spec["spec_id"], seed)
            source_success = (source_run / "SUCCESS").is_file()
            system_success = (output_run / "SUCCESS").is_file()
            source_success_count += int(source_success)
            success_count += int(system_success)
            manifest = output_run / "manifest.json"
            manifest_count += int(manifest.is_file())
            if source_success != system_success:
                issues.append(
                    f"source/system success mismatch: {spec['spec_id']} seed={seed}"
                )
            if system_success:
                for relative in required_success_files:
                    if not (output_run / relative).is_file():
                        issues.append(
                            f"missing {relative}: {spec['spec_id']} seed={seed}"
                        )
                metrics_path = output_run / "metrics/per_run.json"
                if metrics_path.is_file():
                    values = json.loads(metrics_path.read_text(encoding="utf-8"))
                    for metric in METRICS[3:]:
                        value = values.get(metric)
                        if not isinstance(value, (int, float)) or not math.isfinite(
                            float(value)
                        ):
                            issues.append(
                                f"invalid {metric}: {spec['spec_id']} seed={seed}"
                            )
    planned = len(specs) * len(seeds)
    package = (
        json.loads(
            (annotation_root / "package_manifest.json").read_text(encoding="utf-8")
        )
        if (annotation_root / "package_manifest.json").is_file()
        else {}
    )
    response_count = len(
        list((annotation_root / "spatial_aqs_raw").glob("*/pass_*.json"))
    )
    if (
        package.get("planned_pairs") != planned
        or package.get("successful_pairs") != success_count
    ):
        issues.append("spatial package counts do not match adapter runs")
    if response_count != success_count * int(load_protocol()["spatial_aqs"]["passes"]):
        issues.append(
            f"spatial response count={response_count}, expected={success_count * 3}"
        )
    summary_path = results_root / "summary.json"
    if not summary_path.is_file():
        issues.append("summary.json missing")
    else:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if (
            summary.get("planned_pairs") != planned
            or summary.get("successful_pairs") != success_count
        ):
            issues.append("summary counts do not match adapter runs")
    result = {
        "audited_at_utc": utc_now(),
        "trial": trial,
        "passed": not issues,
        "issues": issues,
        "counts": {
            "planned_pairs": planned,
            "source_successful_pairs": source_success_count,
            "successful_pairs": success_count,
            "manifest_pairs": manifest_count,
            "spatial_responses": response_count,
        },
        "source_summary_sha256": sha256_file(source_results / "summary.json"),
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "adapter_sha256": sha256_file(Path(__file__)),
    }
    atomic_json(results_root / "audit.json", result)
    print(
        f"TABLE4_IO_ADAPTER_AUDIT_COMPLETE {json.dumps(result, sort_keys=True)}",
        flush=True,
    )
    return result


def freeze() -> dict[str, Any]:
    _, _, _, _, _, pilot_results = trial_paths("pilot")
    pilot_audit = json.loads((pilot_results / "audit.json").read_text(encoding="utf-8"))
    pilot_summary = json.loads(
        (pilot_results / "summary.json").read_text(encoding="utf-8")
    )
    if not pilot_audit.get("passed") or pilot_summary.get("planned_pairs") != 10:
        raise RuntimeError("A passing 10-pair pilot is required before formal freeze")
    protocol = load_protocol()
    protocol["status"] = "formal_frozen"
    protocol["frozen_after_pilot_at_utc"] = utc_now()
    atomic_json(PROTOCOL_PATH, protocol)
    files = [
        Path(__file__),
        PROTOCOL_PATH,
        PROMPT_PATH,
        SOURCE_LOCK,
        SOURCE_SUMMARY,
        SOURCE_AUDIT,
        NAVMESH_EVALUATOR,
        RECAST_BINARY,
        MODEL_MANIFEST,
    ]
    lock = {
        "method": protocol["method"],
        "display_name": protocol["display_name"],
        "track": protocol["track"],
        "frozen_at_utc": utc_now(),
        "pilot_summary_sha256": sha256_file(pilot_results / "summary.json"),
        "pilot_audit_sha256": sha256_file(pilot_results / "audit.json"),
        "files": {rel(path): sha256_file(path) for path in files},
        "no_human_postprocessing": True,
    }
    atomic_json(LOCK_PATH, lock)
    verify_lock()
    print(
        f"TABLE4_IO_ADAPTER_FREEZE_COMPLETE {json.dumps(lock, sort_keys=True)}",
        flush=True,
    )
    return lock


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "package", "aggregate", "audit"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--trial", choices=("pilot", "formal"), required=True)
    score = subparsers.add_parser("score-spatial")
    score.add_argument("--trial", choices=("pilot", "formal"), required=True)
    score.add_argument("--gpu", type=int, default=0)
    score.add_argument("--port", type=int, default=8144)
    score.add_argument("--request-workers", type=int, default=4)
    score.add_argument("--external-vllm", action="store_true")
    wait_score = subparsers.add_parser("wait-score-spatial")
    wait_score.add_argument("--trial", choices=("pilot", "formal"), required=True)
    wait_score.add_argument(
        "--candidate-gpus", nargs="+", type=int, default=[0, 1, 2, 3]
    )
    wait_score.add_argument("--port", type=int, default=8144)
    wait_score.add_argument("--request-workers", type=int, default=4)
    wait_score.add_argument("--poll-seconds", type=int, default=30)
    wait_score.add_argument("--stable-samples", type=int, default=3)
    subparsers.add_parser("freeze")
    subparsers.add_parser("verify-lock")
    args = parser.parse_args()
    if args.command == "build":
        build_trial(args.trial)
    elif args.command == "package":
        make_spatial_package(args.trial)
    elif args.command == "score-spatial":
        start_and_score(
            args.trial, args.gpu, args.port, args.request_workers, args.external_vllm
        )
    elif args.command == "wait-score-spatial":
        wait_and_score(
            args.trial,
            args.candidate_gpus,
            args.port,
            args.request_workers,
            args.poll_seconds,
            args.stable_samples,
        )
    elif args.command == "aggregate":
        aggregate(args.trial)
    elif args.command == "audit":
        result = audit(args.trial)
        raise SystemExit(0 if result["passed"] else 1)
    elif args.command == "freeze":
        freeze()
    elif args.command == "verify-lock":
        verify_lock()
        print("TABLE4_IO_ADAPTER_LOCK_OK")


if __name__ == "__main__":
    main()
