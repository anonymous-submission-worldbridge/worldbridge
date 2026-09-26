#!/usr/bin/env python3
"""Reconstruct one MetaUrban spec's frozen seeds and evaluate Table 3."""

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
import json
import math
import os
import platform
import random
import shutil
import sys
import traceback
from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry import Polygon, box


REPO = _BASELINE_PROJECT_ROOT
sys.path.insert(0, str(REPO))

from baselines.methods.metaurban.geometry.common import BASELINES
from baselines.methods.metaurban.geometry.common import PACKAGE
from baselines.methods.metaurban.geometry.common import PROTOCOL
from baselines.methods.metaurban.geometry.common import SOURCE
from baselines.methods.metaurban.geometry.common import TABLE2
from baselines.methods.metaurban.geometry.common import TABLE3
from baselines.methods.metaurban.geometry.common import atomic_json
from baselines.methods.metaurban.geometry.common import classify_table2
from baselines.methods.metaurban.geometry.common import ensure_below_baselines
from baselines.methods.metaurban.geometry.common import load_jsonl
from baselines.methods.metaurban.geometry.common import read_json
from baselines.methods.metaurban.geometry.common import sha256
from baselines.methods.metaurban.geometry.common import utc_now
from baselines.methods.metaurban.geometry.metrics.geometry import box_mesh
from baselines.methods.metaurban.geometry.metrics.geometry import clean_union
from baselines.methods.metaurban.geometry.metrics.geometry import footprint
from baselines.methods.metaurban.geometry.metrics.geometry import merge_meshes
from baselines.methods.metaurban.geometry.metrics.geometry import obb
from baselines.methods.metaurban.geometry.metrics.geometry import overlap_volume
from baselines.methods.metaurban.geometry.metrics.geometry import polygon_parts
from baselines.methods.metaurban.geometry.metrics.geometry import sat_overlap
from baselines.methods.metaurban.geometry.metrics.geometry import surface_mesh
from baselines.methods.metaurban.geometry.metrics.geometry import write_ply
from baselines.methods.metaurban.geometry.metrics.navigation import (
    evaluate as evaluate_navigation,
)


os.environ.setdefault("METAURBANHOME", str(SOURCE))
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

REGION_ATTRIBUTES = {
    "main_sidewalk": "sidewalks",
    "nearroad_sidewalk": "sidewalks_near_road",
    "nearroad_buffer_sidewalk": "sidewalks_near_road_buffer",
    "farfromroad_sidewalk": "sidewalks_farfrom_road",
    "farfromroad_buffer_sidewalk": "sidewalks_farfrom_road_buffer",
    "valid_region": "valid_region",
    "crosswalk": "crosswalks",
}


def slug(value: str) -> str:
    return "".join(
        character.lower() if character.isalnum() else "_" for character in value
    ).strip("_")


def jsonable(value):
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if hasattr(value, "tolist"):
        return jsonable(value.tolist())
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def implementation_hashes() -> dict[str, str]:
    paths = [
        Path(__file__),
        PACKAGE / "metrics/geometry.py",
        PACKAGE / "metrics/navigation.py",
        PROTOCOL / "urban_specs.jsonl",
        PROTOCOL / "agent.json",
        PROTOCOL / "protocol.json",
        PROTOCOL / "object_roles.json",
        PROTOCOL / "support_rules.json",
        PROTOCOL / "collision_exceptions.json",
        PROTOCOL / "containers.json",
        PROTOCOL / "reference_thresholds.json",
        BASELINES / "methods/metaurban/adapter.py",
        BASELINES / "methods/metaurban/protocol/generation/metaurban_protocol.yaml",
    ]
    recast_binary = next((PACKAGE / "recast").glob("recast*.so"))
    paths.append(recast_binary)
    return {str(path.relative_to(BASELINES)): sha256(path) for path in paths}


def load_spec(spec_id: str) -> dict:
    for spec in load_jsonl(PROTOCOL / "urban_specs.jsonl"):
        if spec["spec_id"] == spec_id:
            return spec
    raise KeyError(spec_id)


def environment_config(native: dict, sensor_class) -> dict:
    return {
        # A worker evaluates up to four consecutive logical seeds for one
        # specification.  MetaUrban validates reset seeds against this window.
        "map": native["native_map"],
        "start_seed": native["method_seed"],
        "num_scenarios": 4,
        "tiny": False,
        "use_render": False,
        "image_observation": True,
        "image_on_cuda": False,
        "sensors": {"rgb_geometry": (sensor_class, 32, 32)},
        "vehicle_config": {
            "image_source": "rgb_geometry",
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


def polygons_from_map(scene_map, roi: Polygon):
    raw: dict[str, list[Polygon]] = {}
    unions = {}
    for region_name, attribute in REGION_ATTRIBUTES.items():
        polygons = []
        for item in getattr(scene_map, attribute, {}).values():
            points = item.get("polygon", [])
            try:
                polygon = Polygon(
                    [(float(point[0]), float(point[1])) for point in points]
                ).buffer(0)
            except Exception:
                continue
            clipped = polygon.intersection(roi)
            polygons.extend(polygon_parts(clipped))
        raw[region_name] = polygons
        unions[region_name] = clean_union(polygons)
    return raw, unions


def rings(geometry) -> list[list[list[float]]]:
    return [
        [[float(x), float(y)] for x, y in list(part.exterior.coords)[:-1]]
        for part in polygon_parts(geometry)
        if part.area > 1e-8
    ]


def scene_signature(env) -> dict:
    blocks = []
    for block in env.current_map.blocks:
        row = {"id": block.ID, "class": type(block).__name__}
        for attribute in ("positive_basic_lane", "negative_basic_lane"):
            lane = getattr(block, attribute, None)
            if lane is not None:
                row[attribute] = {
                    "start": [float(value) for value in lane.position(0.0, 0.0)],
                    "end": [
                        float(value) for value in lane.position(float(lane.length), 0.0)
                    ],
                    "length_m": float(lane.length),
                }
        blocks.append(row)
    return {
        "blocks": blocks,
        "static_object_count": int(env.engine.asset_manager.count),
    }


def verify_regeneration(source_run: Path, env, method_seed: int) -> dict:
    saved = read_json(source_run / "scene/scene.json")
    current = scene_signature(env)
    failures = []
    if int(saved.get("method_seed", -1)) != method_seed:
        failures.append("method_seed")
    if int(saved.get("static_object_count", -1)) != current["static_object_count"]:
        failures.append("static_object_count")
    saved_blocks = saved.get("blocks", [])
    if [row.get("id") for row in saved_blocks] != [
        row.get("id") for row in current["blocks"]
    ]:
        failures.append("block_ids")
    for saved_block, current_block in zip(saved_blocks, current["blocks"]):
        for attribute in ("positive_basic_lane", "negative_basic_lane"):
            if attribute in saved_block:
                if attribute not in current_block:
                    failures.append(f"{saved_block.get('id')}:{attribute}:missing")
                    continue
                for field in ("start", "end"):
                    if not np.allclose(
                        saved_block[attribute][field],
                        current_block[attribute][field],
                        atol=1e-5,
                    ):
                        failures.append(f"{saved_block.get('id')}:{attribute}:{field}")
    return {"matched": not failures, "failures": failures, "current": current}


def visible_bounds(item, world) -> tuple[list[list[float]], str]:
    found = item.origin.getTightBounds(world)
    if found:
        lower, upper = found
        values = [[float(value) for value in lower], [float(value) for value in upper]]
        if all(math.isfinite(value) for row in values for value in row):
            return values, "panda3d_final_tight_bounds"
    proxy = obb(
        item.position, [item.LENGTH, item.WIDTH, item.HEIGHT], item.heading_theta
    )
    corners = np.asarray(proxy["corners"], dtype=float)
    return [
        corners.min(axis=0).tolist(),
        corners.max(axis=0).tolist(),
    ], "bullet_proxy_fallback"


def extract_instances(
    env, roi: Polygon, roles: dict, containers: dict
) -> tuple[list[dict], int]:
    excluded = set(
        read_json(PROTOCOL / "collision_exceptions.json")["excluded_categories"]
    )
    structural = set(roles["structural"])
    flexible = set(roles["thin_or_flexible"])
    provisional = []
    for item in env.engine.asset_manager.spawned_objects.values():
        metadata = item.asset_metainfo
        semantic = str(
            metadata.get("general", {}).get("detail_type")
            or metadata.get("CLASS_NAME")
            or "unknown"
        )
        proxy = obb(
            item.position, [item.LENGTH, item.WIDTH, item.HEIGHT], item.heading_theta
        )
        if not footprint(proxy).intersects(roi):
            continue
        bounds, bounds_source = visible_bounds(item, env.engine.origin)
        if semantic in structural or bool(getattr(item, "is_building", False)):
            role = "structural"
        elif semantic in flexible:
            role = "thin_or_flexible"
        else:
            role = "placed_object"
        provisional.append(
            {
                "semantic": semantic,
                "filename": str(item.filename),
                "native_position_xy_m": [float(value) for value in item.position],
                "native_origin_z_m": float(item.get_z()),
                "heading_rad": float(item.heading_theta),
                "size_xyz_m": [
                    float(item.LENGTH),
                    float(item.WIDTH),
                    float(item.HEIGHT),
                ],
                "role": role,
                "container_types": containers.get(semantic, containers["fallback"]),
                "support_parent": "native_pedestrian_surface",
                "mount_type": "gravity",
                "include_collision": role != "thin_or_flexible"
                and semantic not in excluded,
                "include_floating": role == "placed_object",
                "include_oob": role == "placed_object",
                "visual_bounds_world_m": bounds,
                "visual_bounds_source": bounds_source,
                "mesh_node": str(item.filename),
                "collision_proxy": proxy,
                "source": "native",
                "native_geom_node_count": int(
                    item.origin.findAllMatches("**/+GeomNode").getNumPaths()
                ),
            }
        )
    provisional.sort(
        key=lambda row: (
            row["semantic"],
            row["filename"],
            tuple(round(value, 5) for value in row["native_position_xy_m"]),
            round(row["heading_rad"], 6),
        )
    )
    counts: dict[str, int] = {}
    for row in provisional:
        key = slug(row["semantic"]) or "object"
        counts[key] = counts.get(key, 0) + 1
        row["instance_id"] = f"{key}_{counts[key]:04d}"
    return provisional, int(env.engine.asset_manager.count)


def union_for(names: list[str], region_unions: dict):
    return clean_union(region_unions[name] for name in names if name in region_unions)


def structural_metrics(
    spec: dict,
    instances: list[dict],
    region_unions: dict,
    walkable,
    native_count: int,
    expected_count: int,
):
    collision_config = read_json(PROTOCOL / "collision_exceptions.json")
    support_config = read_json(PROTOCOL / "support_rules.json")
    root_categories = set(support_config["root_embedding_categories"])
    eligible = [
        row
        for row in instances
        if row["role"] == "placed_object" and row["include_collision"]
    ]
    colliders = [row for row in instances if row["include_collision"]]
    collision_ids: set[str] = set()
    pairs = []
    for left_index, left in enumerate(colliders):
        left_eligible = left["role"] == "placed_object"
        for right in colliders[left_index + 1 :]:
            right_eligible = right["role"] == "placed_object"
            if not left_eligible and not right_eligible:
                continue
            left_proxy, right_proxy = left["collision_proxy"], right["collision_proxy"]
            left_corners = np.asarray(left_proxy["corners"])
            right_corners = np.asarray(right_proxy["corners"])
            if np.any(left_corners.max(axis=0) < right_corners.min(axis=0)) or np.any(
                right_corners.max(axis=0) < left_corners.min(axis=0)
            ):
                continue
            overlaps, depth = sat_overlap(left_proxy, right_proxy)
            if not overlaps:
                continue
            volume = overlap_volume(left_proxy, right_proxy)
            fraction = volume / max(
                min(left_proxy["volume_m3"], right_proxy["volume_m3"]), 1e-12
            )
            significant = bool(
                depth > float(collision_config["penetration_depth_m"])
                or (
                    volume > float(collision_config["overlap_volume_m3"])
                    and fraction
                    > float(collision_config["smaller_object_volume_fraction"])
                )
            )
            pairs.append(
                {
                    "a": left["instance_id"],
                    "b": right["instance_id"],
                    "penetration_depth_m": depth,
                    "overlap_volume_m3": volume,
                    "smaller_volume_fraction": fraction,
                    "significant": significant,
                }
            )
            if significant:
                if left_eligible:
                    collision_ids.add(left["instance_id"])
                if right_eligible:
                    collision_ids.add(right["instance_id"])

    support_edges = []
    floating_ids = set()
    valid_support = 0
    for row in eligible:
        semantic = row["semantic"]
        container = union_for(row["container_types"], region_unions)
        object_footprint = footprint(row["collision_proxy"])
        center = object_footprint.centroid
        projection_fraction = float(
            object_footprint.intersection(container).area
            / max(object_footprint.area, 1e-12)
        )
        gap = float(row["visual_bounds_world_m"][0][2]) - float(
            support_config["support_surface_z_m"]
        )
        embedding_limit = float(
            support_config["root_maximum_embedding_m"]
            if semantic in root_categories
            else support_config["maximum_embedding_m"]
        )
        floating = gap > float(support_config["maximum_gap_m"])
        if floating:
            floating_ids.add(row["instance_id"])
        embedded = gap < -embedding_limit
        if embedded:
            collision_ids.add(row["instance_id"])
            pairs.append(
                {
                    "a": row["instance_id"],
                    "b": "native_pedestrian_surface",
                    "penetration_depth_m": -gap,
                    "overlap_volume_m3": float(object_footprint.area * -gap),
                    "smaller_volume_fraction": None,
                    "significant": True,
                    "exception_embedding_limit_m": embedding_limit,
                }
            )
        valid = bool(
            not floating
            and not embedded
            and center.within(container.buffer(1e-8))
            and projection_fraction
            >= float(support_config["minimum_projection_fraction"])
            and row["instance_id"] not in collision_ids
        )
        if valid:
            valid_support += 1
        support_edges.append(
            {
                "child": row["instance_id"],
                "parent": "native_pedestrian_surface",
                "mount_type": "gravity",
                "gap_m": gap,
                "embedding_limit_m": embedding_limit,
                "projection_fraction": projection_fraction,
                "center_in_container": bool(center.within(container.buffer(1e-8))),
                "floating": floating,
                "embedded": embedded,
                "valid": valid,
            }
        )

    oob_rows = []
    oob_ids = set()
    for row in eligible:
        container = union_for(row["container_types"], region_unions)
        object_footprint = footprint(row["collision_proxy"])
        outside_fraction = float(
            object_footprint.difference(container).area
            / max(object_footprint.area, 1e-12)
        )
        center_inside = bool(object_footprint.centroid.within(container.buffer(1e-8)))
        is_oob = bool(not center_inside or outside_fraction > 0.01)
        if is_oob:
            oob_ids.add(row["instance_id"])
        oob_rows.append(
            {
                "instance_id": row["instance_id"],
                "container_types": row["container_types"],
                "outside_area_fraction": outside_fraction,
                "centroid_inside": center_inside,
                "oob": is_oob,
            }
        )

    semantic_counts: dict[str, int] = {}
    for row in instances:
        semantic_counts[row["semantic"]] = semantic_counts.get(row["semantic"], 0) + 1
    furniture = {
        "Lamp_post",
        "TrashCan",
        "Mailbox",
        "Telephone_booth",
        "FireHydrant",
        "Bench",
        "Traffic_sign",
        "Bollard",
        "Traffic_light",
    }
    coverage = {
        "building": sum(
            value for key, value in semantic_counts.items() if key == "Building"
        ),
        "tree": sum(value for key, value in semantic_counts.items() if key == "Tree"),
        "street_furniture": sum(
            value for key, value in semantic_counts.items() if key in furniture
        ),
    }
    coverage_rows = [
        {
            "group": group,
            "count": int(coverage.get(group, 0)),
            "passed": coverage.get(group, 0) > 0,
        }
        for group in spec["required_instance_groups"]
    ]
    contract = bool(
        expected_count == native_count
        and len(eligible) > 0
        and walkable.area > 1.0
        and all(row["passed"] for row in coverage_rows)
        and all(
            row["visual_bounds_source"] == "panda3d_final_tight_bounds"
            for row in eligible
        )
    )
    denominator = len(eligible)
    payload = {
        "method": "metaurban",
        "domain": "urban",
        "spec_id": spec["spec_id"],
        "eligible_objects": denominator,
        "collision_objects": len(collision_ids),
        "collision_rate": 100.0 * len(collision_ids) / denominator
        if denominator
        else 100.0,
        "support_required_objects": denominator,
        "floating_objects": len(floating_ids),
        "floating_rate": 100.0 * len(floating_ids) / denominator
        if denominator
        else 100.0,
        "oob_objects": len(oob_ids),
        "oob_rate": 100.0 * len(oob_ids) / denominator if denominator else 100.0,
        "required_support_edges": denominator,
        "valid_support_edges": valid_support,
        "support_validity": 100.0 * valid_support / denominator if denominator else 0.0,
        "pairs": pairs,
        "support_edges": support_edges,
        "oob_details": oob_rows,
        "instance_coverage": coverage_rows,
        "semantic_counts": semantic_counts,
        "native_scene_object_count": native_count,
        "table2_expected_object_count": expected_count,
        "walkable_reference_area_m2": float(walkable.area),
        "output_contract_passed": contract,
        "failures": [] if contract else ["output_contract_failed"],
    }
    return payload


def save_geometry(
    run_dir: Path, instances: list[dict], walkable, structural: dict
) -> dict:
    canonical = run_dir / "scene/canonical"
    canonical.mkdir(parents=True, exist_ok=True)
    building_rows = [
        row
        for row in instances
        if row["role"] == "structural" and row["include_collision"]
    ]
    placed_rows = [
        row
        for row in instances
        if row["role"] == "placed_object" and row["include_collision"]
    ]
    building_footprints = clean_union(
        footprint(row["collision_proxy"]) for row in building_rows
    )
    placed_footprints = clean_union(
        footprint(row["collision_proxy"]) for row in placed_rows
    )
    reference_surface = walkable.difference(building_footprints).buffer(0)
    final_surface = reference_surface.difference(placed_footprints).buffer(0)
    (
        reference_surface_vertices,
        reference_surface_faces,
        reference_triangles,
    ) = surface_mesh(reference_surface, 0.0)
    final_surface_vertices, final_surface_faces, final_triangles = surface_mesh(
        final_surface, 0.0
    )
    building_meshes = [box_mesh(row["collision_proxy"]) for row in building_rows]
    placed_meshes = [box_mesh(row["collision_proxy"]) for row in placed_rows]
    reference_vertices, reference_faces = merge_meshes(
        [(reference_surface_vertices, reference_surface_faces), *building_meshes]
    )
    final_vertices, final_faces = merge_meshes(
        [
            (final_surface_vertices, final_surface_faces),
            *building_meshes,
            *placed_meshes,
        ]
    )
    np.savez_compressed(
        canonical / "empty_reference_geometry.npz",
        vertices=reference_vertices,
        faces=reference_faces,
    )
    np.savez_compressed(
        canonical / "collision_geometry.npz", vertices=final_vertices, faces=final_faces
    )
    write_ply(canonical / "empty_reference.ply", reference_vertices, reference_faces)
    write_ply(canonical / "collision.ply", final_vertices, final_faces)
    atomic_json(
        canonical / "instances.json",
        {
            "coordinate_system": "right-handed-z-up",
            "unit": "meter",
            "instances": instances,
        },
    )
    atomic_json(
        canonical / "transform.json",
        {
            "source": "MetaUrban right-handed Z-up meters",
            "matrix_source_to_canonical": np.eye(4).tolist(),
        },
    )
    manifest = {
        "representation": "native instances plus frozen Bullet OBB canonical proxies",
        "walkable_triangle_count": len(reference_triangles),
        "final_walkable_triangle_count": len(final_triangles),
        "reference_surface_area_m2": float(reference_surface.area),
        "final_surface_area_m2": float(final_surface.area),
        "ground_obstacle_holes": "exact_obb_footprints_before_recast_agent_erosion",
        "reference_vertices": len(reference_vertices),
        "reference_faces": len(reference_faces),
        "final_vertices": len(final_vertices),
        "final_faces": len(final_faces),
        "placed_obstacle_count": len(placed_meshes),
        "structural_obstacle_count": len(building_meshes),
        "files": {},
    }
    for name in (
        "instances.json",
        "transform.json",
        "empty_reference_geometry.npz",
        "collision_geometry.npz",
        "empty_reference.ply",
        "collision.ply",
    ):
        manifest["files"][name] = sha256(canonical / name)
    atomic_json(canonical / "geometry_manifest.json", manifest)
    return manifest


def evaluate_seed(
    env, spec: dict, logical_seed: int, hashes: dict, assigned_gpu: int, data_root: Path
) -> dict:
    source_run = TABLE2 / spec["spec_id"] / f"seed_{logical_seed}"
    source_ok, source_status = classify_table2(source_run)
    if not source_ok:
        raise RuntimeError(f"Table 2 source is not reusable: {source_status}")
    native = read_json(source_run / "input/native_input.json")
    method_seed = int(native["method_seed"])
    random.seed(method_seed)
    np.random.seed(method_seed)
    import torch

    torch.manual_seed(method_seed)
    torch.cuda.manual_seed_all(method_seed)
    env.reset(seed=method_seed)
    gsg = env.engine.win.getGsg()
    renderer = {
        "vendor": gsg.getDriverVendor(),
        "renderer": gsg.getDriverRenderer(),
        "version": gsg.getDriverVersion(),
    }
    if "nvidia" not in f"{renderer['vendor']} {renderer['renderer']}".lower():
        raise RuntimeError(f"non-NVIDIA OpenGL renderer: {renderer}")
    regeneration = verify_regeneration(source_run, env, method_seed)
    if not regeneration["matched"]:
        raise RuntimeError(
            f"Table 2 deterministic regeneration mismatch: {regeneration['failures']}"
        )

    target_block = env.current_map.blocks[-1]
    lane = getattr(target_block, "positive_basic_lane", None)
    if lane is None:
        raise RuntimeError("final native block has no positive_basic_lane")
    center = np.asarray(lane.position(float(lane.length), 0.0), dtype=float)
    roi = box(center[0] - 56.0, center[1] - 56.0, center[0] + 56.0, center[1] + 56.0)
    raw_regions, region_unions = polygons_from_map(env.current_map, roi)
    walkable = clean_union(region_unions.values()).intersection(roi).buffer(0)
    if walkable.is_empty:
        raise RuntimeError("empty native pedestrian reference in ROI")
    largest = max(polygon_parts(walkable), key=lambda value: value.area)
    spawn = largest.representative_point()

    roles = read_json(PROTOCOL / "object_roles.json")
    containers = read_json(PROTOCOL / "containers.json")
    instances, native_count = extract_instances(env, roi, roles, containers)
    expected_count = int(
        read_json(source_run / "scene/scene.json")["static_object_count"]
    )
    structural = structural_metrics(
        spec, instances, region_unions, walkable, native_count, expected_count
    )

    run_dir = ensure_below_baselines(
        data_root / spec["spec_id"] / f"seed_{logical_seed}"
    )
    (run_dir / "input").mkdir(parents=True, exist_ok=True)
    (run_dir / "scene/raw").mkdir(parents=True, exist_ok=True)
    (run_dir / "metrics").mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_run / "input/spec.json", run_dir / "scene/raw/table2_spec.json")
    shutil.copy2(
        source_run / "input/native_input.json", run_dir / "input/native_input.json"
    )
    atomic_json(run_dir / "input/spec.json", spec)
    boundary = {
        "coordinate_system": "right-handed-z-up",
        "unit": "meter",
        "roi_center_xy_m": center.tolist(),
        "roi_xy_m": [
            [center[0] - 56.0, center[1] - 56.0],
            [center[0] + 56.0, center[1] - 56.0],
            [center[0] + 56.0, center[1] + 56.0],
            [center[0] - 56.0, center[1] + 56.0],
        ],
        "walkable_polygons_xy_m": rings(walkable),
        "region_polygons_xy_m": {
            name: rings(geometry) for name, geometry in region_unions.items()
        },
        "structural_spawn_candidate_m": [float(spawn.x), float(spawn.y), 0.0],
        "spawn_policy": spec["spawn_policy"],
        "floor_z_m": 0.0,
        "native_support_surface_z_m": 0.15,
        "target_block": {"id": target_block.ID, "class": type(target_block).__name__},
    }
    atomic_json(run_dir / "input/boundaries.json", boundary)
    atomic_json(
        run_dir / "scene/raw/source.json",
        {
            "table2_run": str(source_run),
            "table2_manifest_sha256": sha256(source_run / "run_manifest.json"),
            "table2_scene_descriptor_sha256": sha256(source_run / "scene/scene.json"),
            "regeneration": regeneration,
        },
    )
    atomic_json(run_dir / "metrics/structural.json", structural)
    geometry_manifest = save_geometry(run_dir, instances, walkable, structural)
    navigation = evaluate_navigation(
        run_dir, PROTOCOL / "agent.json", PROTOCOL / "reference_thresholds.json"
    )
    manifest = {
        "method": "metaurban",
        "domain": "urban",
        "track": "structured_physics_ready",
        "spec_id": spec["spec_id"],
        "logical_seed": logical_seed,
        "method_seed": method_seed,
        "source_table2_status": source_status,
        "source_table2_run": str(source_run),
        "reuse_status": "reused_manifest_native_input_and_deterministically_reconstructed_geometry",
        "table2_render_regenerated": False,
        "asset_mode": "full",
        "regeneration_match": True,
        "canonical_status": "success",
        "evaluation_status": "success",
        "output_contract_passed": structural["output_contract_passed"],
        "navmesh_success": navigation["navmesh_success"],
        "hardware": {
            "hostname": platform.node(),
            "assigned_gpu": assigned_gpu,
            "gpu_used_for_panda3d_geometry_load": True,
            "opengl": renderer,
        },
        "implementation_hashes": hashes,
        "geometry_manifest": geometry_manifest,
        "completed_at_utc": utc_now(),
    }
    atomic_json(run_dir / "run_manifest.json", manifest)
    for marker in ("GENERATION_SUCCESS", "CANONICAL_SUCCESS", "EVALUATION_SUCCESS"):
        (run_dir / marker).touch()
    return {
        "spec_id": spec["spec_id"],
        "seed": logical_seed,
        "objects": structural["eligible_objects"],
        "collision": structural["collision_rate"],
        "floating": structural["floating_rate"],
        "oob": structural["oob_rate"],
        "support": structural["support_validity"],
        "nav": navigation["navigable_area_ratio"],
        "connected": navigation["connected_area_ratio"],
        "nav_success": navigation["navmesh_success"],
        "valid": navigation["valid"],
    }


def current(run_dir: Path, hashes: dict) -> bool:
    required = [
        run_dir / "EVALUATION_SUCCESS",
        run_dir / "metrics/structural.json",
        run_dir / "metrics/navigability.json",
        run_dir / "run_manifest.json",
    ]
    if not all(path.is_file() for path in required):
        return False
    try:
        return (
            read_json(run_dir / "run_manifest.json").get("implementation_hashes")
            == hashes
        )
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec-id", required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3])
    parser.add_argument("--gpu", type=int, required=True)
    parser.add_argument("--data-root", type=Path, default=TABLE3)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if any(seed not in (0, 1, 2, 3) for seed in args.seeds):
        parser.error("seeds must be chosen from 0,1,2,3")
    data_root = ensure_below_baselines(args.data_root)
    hashes = implementation_hashes()
    spec = load_spec(args.spec_id)
    pending = [
        seed
        for seed in args.seeds
        if args.force or not current(data_root / args.spec_id / f"seed_{seed}", hashes)
    ]
    if not pending:
        print(
            json.dumps(
                {"spec_id": args.spec_id, "skipped": sorted(args.seeds)}, sort_keys=True
            )
        )
        return 0

    import torch
    from metaurban.component.sensors.rgb_camera import RGBCamera
    from metaurban.envs import SidewalkStaticMetaUrbanEnv
    from metaurban.envs.base_env import BASE_DEFAULT_CONFIG
    from metaurban.engine.engine_utils import close_engine
    from metaurban.engine.engine_utils import initialize_engine

    first_native = read_json(
        TABLE2 / spec["spec_id"] / f"seed_{pending[0]}" / "input/native_input.json"
    )
    warmup = BASE_DEFAULT_CONFIG.copy()
    warmup["debug"] = True
    initialize_engine(warmup)
    close_engine()
    env = SidewalkStaticMetaUrbanEnv(environment_config(first_native, RGBCamera))
    failures = []
    try:
        for seed in pending:
            try:
                result = evaluate_seed(env, spec, seed, hashes, args.gpu, data_root)
                print(
                    "METAURBAN_TABLE3 " + json.dumps(result, sort_keys=True), flush=True
                )
            except Exception as error:
                failures.append(
                    {
                        "seed": seed,
                        "type": type(error).__name__,
                        "message": str(error),
                        "traceback": traceback.format_exc(),
                    }
                )
                print(
                    "METAURBAN_TABLE3_FAILURE "
                    + json.dumps(failures[-1], sort_keys=True),
                    flush=True,
                )
    finally:
        env.close()
    if failures:
        atomic_json(
            PACKAGE / f"results/failure_{spec['spec_id']}.json",
            {"spec_id": spec["spec_id"], "failures": failures},
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
