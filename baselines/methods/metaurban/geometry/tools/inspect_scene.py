#!/usr/bin/env python3
"""Inspect one frozen MetaUrban Table-2 scene without writing scene outputs."""

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
from collections import Counter, defaultdict
import json
import os
import random
import sys
from pathlib import Path

import numpy as np


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
SOURCE = BASELINES / "sources/metaurban"
TABLE2 = BASELINES / "data/table2/urban/metaurban"
sys.path.insert(0, str(SOURCE))
os.environ.setdefault("METAURBANHOME", str(SOURCE))


def bounds(node_path, relative_to):
    found = node_path.getTightBounds(relative_to)
    if not found:
        return None
    lower, upper = found
    return [[float(value) for value in lower], [float(value) for value in upper]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec-id", default="urban_residential_four_way_00")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()
    source_run = TABLE2 / args.spec_id / f"seed_{args.seed}"
    native = json.loads((source_run / "input/native_input.json").read_text())

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
    warmup = BASE_DEFAULT_CONFIG.copy()
    warmup["debug"] = True
    initialize_engine(warmup)
    close_engine()
    config = {
        "map": native["native_map"],
        "start_seed": native["method_seed"],
        "num_scenarios": 1,
        "tiny": False,
        "use_render": False,
        "image_observation": True,
        "image_on_cuda": False,
        "sensors": {"rgb_probe": (RGBCamera, 32, 32)},
        "vehicle_config": {"image_source": "rgb_probe", "show_lidar": False},
        "interface_panel": [],
        "show_interface": False,
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
    env = SidewalkStaticMetaUrbanEnv(config)
    try:
        env.reset(seed=native["method_seed"])
        manager = env.engine.asset_manager
        rows = []
        counts = Counter()
        positions = defaultdict(list)
        all_objects = sorted(manager.spawned_objects.items())
        for _, item in all_objects:
            semantic = str(
                item.asset_metainfo.get("general", {}).get("detail_type")
                or item.asset_metainfo.get("CLASS_NAME")
                or "unknown"
            )
            counts[semantic] += 1
            positions[semantic].append([float(value) for value in item.position])
        for object_id, item in all_objects[: args.limit]:
            shapes = []
            body = item.body
            for index in range(body.getNumShapes()):
                shape = body.getShape(index)
                transform = body.getShapeTransform(index)
                shapes.append(
                    {
                        "type": type(shape).__name__,
                        "margin": float(shape.getMargin()),
                        "transform_pos": [float(value) for value in transform.getPos()],
                    }
                )
            rows.append(
                {
                    "id": str(object_id),
                    "detail_type": item.asset_metainfo["general"]["detail_type"],
                    "filename": item.filename,
                    "position": [float(value) for value in item.position],
                    "origin_z": float(item.get_z()),
                    "heading": float(item.heading_theta),
                    "size": [float(item.LENGTH), float(item.WIDTH), float(item.HEIGHT)],
                    "origin_bounds_world": bounds(item.origin, env.engine.origin),
                    "geom_count": int(
                        item.origin.findAllMatches("**/+GeomNode").getNumPaths()
                    ),
                    "shapes": shapes,
                }
            )
        blocks = []
        for block in env.current_map.blocks:
            blocks.append(
                {
                    "id": block.ID,
                    "bounds": block.bounding_box,
                    "sidewalk": len(block.sidewalks),
                    "near": len(block.sidewalks_near_road),
                    "near_buffer": len(block.sidewalks_near_road_buffer),
                    "far": len(block.sidewalks_farfrom_road),
                    "far_buffer": len(block.sidewalks_farfrom_road_buffer),
                    "crosswalk": len(block.crosswalks),
                    "valid_region": len(block.valid_region),
                }
            )
        print(
            json.dumps(
                {
                    "count": manager.count,
                    "semantic_counts": dict(sorted(counts.items())),
                    "position_bounds": {
                        key: {
                            "minimum": np.asarray(value).min(axis=0).tolist(),
                            "maximum": np.asarray(value).max(axis=0).tolist(),
                        }
                        for key, value in sorted(positions.items())
                    },
                    "objects": rows,
                    "blocks": blocks,
                },
                indent=2,
                default=str,
            )
        )
    finally:
        env.close()


if __name__ == "__main__":
    main()
