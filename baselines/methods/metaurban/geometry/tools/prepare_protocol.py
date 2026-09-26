#!/usr/bin/env python3
"""Derive and freeze the MetaUrban-only Table 3 protocol from Table 2 specs."""

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


import json
import sys
from pathlib import Path


REPO = _BASELINE_PROJECT_ROOT
sys.path.insert(0, str(REPO))

from baselines.methods.metaurban.geometry.common import BASELINES
from baselines.methods.metaurban.geometry.common import PROTOCOL
from baselines.methods.metaurban.geometry.common import atomic_json
from baselines.methods.metaurban.geometry.common import sha256


def main() -> None:
    PROTOCOL.mkdir(parents=True, exist_ok=True)
    source = BASELINES / "protocol/generation/urban_specs.jsonl"
    target = PROTOCOL / "urban_specs.jsonl"
    rows = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        spec = json.loads(line)
        spec.update(
            {
                "evaluation_roi": {
                    "type": "target_lane_end_centered_square",
                    "local_xy_m": [
                        [-56.0, -56.0],
                        [56.0, -56.0],
                        [56.0, 56.0],
                        [-56.0, 56.0],
                    ],
                    "runtime_translation_source": "final native block positive_basic_lane end",
                },
                "walkable_regions": [
                    "main_sidewalk",
                    "nearroad_sidewalk",
                    "nearroad_buffer_sidewalk",
                    "farfromroad_sidewalk",
                    "farfromroad_buffer_sidewalk",
                    "valid_region",
                    "crosswalk",
                ],
                "spawn_policy": "representative point of the largest connected native empty-reference pedestrian polygon",
                "goal_regions": ["other connected sidewalk branches and crosswalks"],
                "required_instance_groups": ["building", "tree", "street_furniture"],
                "required_support_edges": [
                    {
                        "child_role": "placed_object",
                        "parent_role": "native_pedestrian_surface",
                        "mount": "gravity",
                    }
                ],
                "allowed_boundary_crossings": [
                    "road continuation",
                    "sidewalk continuation",
                    "crosswalk continuation",
                ],
                "domain_metadata": {
                    "evaluation_unit": "target-centered 112 m square",
                    "navigation_agent": "pedestrian",
                    "dynamic_agents_frozen": True,
                },
            }
        )
        rows.append(spec)
    target.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )

    atomic_json(
        PROTOCOL / "agent.json",
        {
            "agent": {
                "height_m": 1.70,
                "radius_m": 0.30,
                "max_climb_m": 0.20,
                "max_slope_deg": 45.0,
            },
            "recast": {
                "cell_size_m": 0.05,
                "cell_height_m": 0.05,
                "partition": "watershed",
                "filter_low_hanging_obstacles": True,
                "filter_ledge_spans": True,
                "filter_low_height_spans": True,
            },
            "postprocess": {
                "connect_components": False,
                "keep_largest_only": False,
                "keep_target_height_band_only": True,
            },
            "spawn": {"horizontal_tolerance_m": 0.30, "vertical_tolerance_m": 0.50},
            "success": {"minimum_reference_area_fraction": 0.01},
        },
    )
    atomic_json(
        PROTOCOL / "object_roles.json",
        {
            "structural": ["Building"],
            "placed_object": [
                "Tree",
                "Lamp_post",
                "TrashCan",
                "Mailbox",
                "Telephone_booth",
                "FireHydrant",
                "Chair",
                "Advertising_board",
                "Bench",
                "Traffic_sign",
                "Bollard",
                "dog",
                "Vending_machine",
                "Bag",
                "Table",
                "Bonsai",
                "Cone",
                "FoodTruck",
                "Bicycle",
                "Bike",
                "Motorcycle",
                "Scooter",
                "Wheelchair",
                "Traffic_light",
            ],
            "thin_or_flexible": ["Vegetation"],
            "nonphysical_visual": [],
            "unknown_policy": "placed_object_and_reported",
        },
    )
    atomic_json(
        PROTOCOL / "support_rules.json",
        {
            "default_mount": "gravity",
            "support_surface_z_m": 0.15,
            "maximum_gap_m": 0.02,
            "maximum_embedding_m": 0.01,
            "minimum_projection_fraction": 0.05,
            "root_embedding_categories": ["Tree", "Vegetation", "Bonsai"],
            "root_maximum_embedding_m": 0.30,
            "visual_bottom_source": "Panda3D final rendered instance tight bounds in world coordinates",
        },
    )
    atomic_json(
        PROTOCOL / "collision_exceptions.json",
        {
            "penetration_depth_m": 0.01,
            "overlap_volume_m3": 0.00001,
            "smaller_object_volume_fraction": 0.005,
            "root_embedding_categories": ["Tree", "Vegetation", "Bonsai"],
            "root_maximum_embedding_m": 0.30,
            "excluded_categories": ["Vegetation"],
            "expected_contacts": ["placed_object:native_pedestrian_surface"],
        },
    )
    atomic_json(
        PROTOCOL / "containers.json",
        {
            "Tree": ["nearroad_sidewalk", "nearroad_buffer_sidewalk", "valid_region"],
            "Lamp_post": ["nearroad_sidewalk", "nearroad_buffer_sidewalk"],
            "TrashCan": ["nearroad_sidewalk", "nearroad_buffer_sidewalk"],
            "Mailbox": ["main_sidewalk"],
            "Telephone_booth": ["main_sidewalk"],
            "FireHydrant": ["nearroad_sidewalk", "nearroad_buffer_sidewalk"],
            "Building": ["valid_region"],
            "Chair": ["farfromroad_sidewalk", "farfromroad_buffer_sidewalk"],
            "Vegetation": ["farfromroad_sidewalk", "farfromroad_buffer_sidewalk"],
            "Advertising_board": [
                "farfromroad_sidewalk",
                "farfromroad_buffer_sidewalk",
            ],
            "Bench": ["farfromroad_sidewalk", "farfromroad_buffer_sidewalk"],
            "Traffic_sign": ["nearroad_sidewalk", "nearroad_buffer_sidewalk"],
            "Bollard": ["nearroad_sidewalk", "nearroad_buffer_sidewalk"],
            "dog": ["main_sidewalk"],
            "Vending_machine": ["main_sidewalk"],
            "Bag": ["main_sidewalk"],
            "Table": ["main_sidewalk"],
            "Bonsai": ["farfromroad_sidewalk", "farfromroad_buffer_sidewalk"],
            "Cone": ["main_sidewalk"],
            "FoodTruck": ["valid_region"],
            "Bicycle": ["valid_region"],
            "Bike": ["valid_region"],
            "Motorcycle": ["valid_region"],
            "Scooter": ["valid_region"],
            "Wheelchair": ["valid_region"],
            "Traffic_light": ["main_sidewalk"],
            "fallback": [
                "main_sidewalk",
                "nearroad_sidewalk",
                "nearroad_buffer_sidewalk",
                "farfromroad_sidewalk",
                "farfromroad_buffer_sidewalk",
                "valid_region",
            ],
        },
    )
    atomic_json(
        PROTOCOL / "protocol.json",
        {
            "protocol_id": "worldbridge-table3-metaurban-urban-v1",
            "method": "metaurban",
            "domain": "urban",
            "track": "structured_physics_ready",
            "planned_specs": 25,
            "seeds": [0, 1, 2, 3],
            "planned_runs": 100,
            "reuse": {
                "source": "baselines/data/table2/urban/metaurban",
                "policy": "reuse formal manifests/native inputs/renders and deterministically reconstruct only missing final engine geometry",
                "regenerate_table2_renders": False,
            },
            "representation": {
                "instances": "native AssetManager stable instances",
                "collision_proxy": "final Bullet box shape reconstructed from native dimensions and pose",
                "support_geometry": "final rendered instance tight bounds",
                "scale": "native MetaUrban meters",
                "coordinate_system": "right-handed Z-up",
            },
            "roi": "112 m square centered at final native block positive lane endpoint",
            "navigation": "native pedestrian-region polygons, rebuilt with frozen external Recast; no island connection or largest-only filtering",
            "aggregation": {
                "order": "mean_over_spec(mean_over_seed(scene_metric))",
                "failure_policy": "itt",
                "bootstrap_repeats": 10000,
                "bootstrap_seed": 20260909,
            },
            "display": {"unit": "percent", "decimals": 1},
            "spec_source_sha256": sha256(source),
            "table3_specs_sha256": sha256(target),
        },
    )
    print(
        json.dumps(
            {"specs": len(rows), "output": str(target), "sha256": sha256(target)},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
