#!/usr/bin/env python3
"""Build the independent 50-scene urban reference suite and freeze thresholds."""

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
import tempfile
from pathlib import Path

import numpy as np
from shapely.geometry import LineString, box
from shapely.ops import unary_union


REPO = _BASELINE_PROJECT_ROOT
sys.path.insert(0, str(REPO))

from baselines.methods.metaurban.geometry.common import BASELINES
from baselines.methods.metaurban.geometry.common import PACKAGE
from baselines.methods.metaurban.geometry.common import PROTOCOL
from baselines.methods.metaurban.geometry.common import atomic_json
from baselines.methods.metaurban.geometry.common import read_json
from baselines.methods.metaurban.geometry.common import sha256
from baselines.methods.metaurban.geometry.metrics.geometry import box_mesh
from baselines.methods.metaurban.geometry.metrics.geometry import clean_union
from baselines.methods.metaurban.geometry.metrics.geometry import footprint
from baselines.methods.metaurban.geometry.metrics.geometry import merge_meshes
from baselines.methods.metaurban.geometry.metrics.geometry import obb
from baselines.methods.metaurban.geometry.metrics.geometry import surface_mesh
from baselines.methods.metaurban.geometry.metrics.navigation import build_recast
from baselines.methods.metaurban.geometry.metrics.navigation import connected_components
from baselines.methods.metaurban.geometry.metrics.navigation import triangle_areas


def walkway(topology: str, variant: int):
    shift = 0.20 * ((variant % 5) - 2)
    horizontal = [
        box(-20, -6.5 + shift, 20, -3.5 + shift),
        box(-20, 3.5 + shift, 20, 6.5 + shift),
    ]
    vertical = [box(-6.5, -20, -3.5, 20), box(3.5, -20, 6.5, 20)]
    crossings = [box(-2.0, -3.5 + shift, 2.0, 3.5 + shift), box(-3.5, -2.0, 3.5, 2.0)]
    if topology == "four_way":
        pieces = horizontal + vertical + crossings
    elif topology == "t_junction":
        pieces = (
            horizontal
            + [box(-6.5, -3.5, -3.5, 20), box(3.5, -3.5, 6.5, 20)]
            + crossings
        )
    elif topology == "main_road_side_road":
        pieces = horizontal + [box(-6.0, 0, -3.5, 20), box(3.5, 0, 6.0, 20)] + crossings
    elif topology == "offset_intersection":
        pieces = horizontal + [
            box(-11, -3.5, -8, 20),
            box(8, -20, 11, 3.5),
            box(-11, -1.5, -8, 1.5),
            box(8, -1.5, 11, 1.5),
        ]
    else:
        diagonal = LineString(
            [(-18, -16 + shift), (-4, -2), (3, 5), (17, 18 - shift)]
        ).buffer(1.5, cap_style=2, join_style=2)
        pieces = horizontal + [diagonal, box(-3, -4, 3, 4)]
    return unary_union(pieces).buffer(0)


def reference_record(topology: str, variant: int) -> dict:
    area = walkway(topology, variant)
    boundary = area.boundary
    rng = np.random.default_rng(
        1000
        + 31 * variant
        + 101
        * [
            "four_way",
            "t_junction",
            "main_road_side_road",
            "offset_intersection",
            "irregular_intersection",
        ].index(topology)
    )
    obstacles = []
    attempts = 0
    target = 8 + variant % 5
    while len(obstacles) < target and attempts < 2000:
        attempts += 1
        min_x, min_y, max_x, max_y = area.bounds
        x, y = rng.uniform(min_x, max_x), rng.uniform(min_y, max_y)
        point = box(x - 0.3, y - 0.3, x + 0.3, y + 0.3)
        # Furniture is valid only when wholly on the pedestrian surface and
        # kept near an edge, leaving a central clear strip wider than the agent.
        if area.covers(point) and boundary.distance(point) < 1.25:
            if all(point.distance(box(*item["bounds"])) > 0.8 for item in obstacles):
                obstacles.append(
                    {"bounds": [x - 0.3, y - 0.3, x + 0.3, y + 0.3], "height_m": 1.0}
                )
    return {
        "reference_id": f"urban_reference_{topology}_{variant:02d}",
        "topology": topology,
        "variant": variant,
        "walkable_wkt": area.wkt,
        "obstacles": obstacles,
        "validation": "deterministic contained non-overlapping edge furniture with clear pedestrian core",
    }


def main() -> None:
    topologies = [
        "four_way",
        "t_junction",
        "main_road_side_road",
        "offset_intersection",
        "irregular_intersection",
    ]
    records = [
        reference_record(topology, variant)
        for topology in topologies
        for variant in range(10)
    ]
    definitions = PROTOCOL / "reference_urban.jsonl"
    definitions.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    config = read_json(PROTOCOL / "agent.json")
    rows = []
    with tempfile.TemporaryDirectory(
        prefix="urban-reference-", dir=BASELINES / "tmp"
    ) as directory:
        temporary = Path(directory)
        for index, record in enumerate(records):
            from shapely import wkt

            area = wkt.loads(record["walkable_wkt"])
            surface_vertices, surface_faces, _ = surface_mesh(area, 0.0)
            obstacle_meshes = []
            obstacle_footprints = []
            for item in record["obstacles"]:
                min_x, min_y, max_x, max_y = item["bounds"]
                proxy = obb(
                    [(min_x + max_x) / 2.0, (min_y + max_y) / 2.0],
                    [max_x - min_x, max_y - min_y, item["height_m"]],
                    0.0,
                )
                obstacle_meshes.append(box_mesh(proxy))
                obstacle_footprints.append(footprint(proxy))
            final_surface = area.difference(clean_union(obstacle_footprints)).buffer(0)
            final_surface_vertices, final_surface_faces, _ = surface_mesh(
                final_surface, 0.0
            )
            final_vertices, final_faces = merge_meshes(
                [(final_surface_vertices, final_surface_faces), *obstacle_meshes]
            )
            reference_path = temporary / f"reference_{index}.npz"
            final_path = temporary / f"final_{index}.npz"
            np.savez_compressed(
                reference_path, vertices=surface_vertices, faces=surface_faces
            )
            np.savez_compressed(final_path, vertices=final_vertices, faces=final_faces)
            ref_vertices, ref_faces, _ = build_recast(reference_path, config)
            nav_vertices, nav_faces, _ = build_recast(final_path, config)
            reference_area = float(triangle_areas(ref_vertices, ref_faces).sum())
            final_area = float(triangle_areas(nav_vertices, nav_faces).sum())
            components = connected_components(nav_vertices, nav_faces)
            largest = components[0]["area_m2"] if components else 0.0
            rows.append(
                {
                    "reference_id": record["reference_id"],
                    "navigable_area_ratio": 100.0
                    * min(1.0, final_area / reference_area),
                    "connected_area_ratio": 100.0 * largest / final_area,
                    "reference_area_m2": reference_area,
                    "final_area_m2": final_area,
                    "component_count": len(components),
                    "obstacle_count": len(record["obstacles"]),
                }
            )
    navigable = np.asarray([row["navigable_area_ratio"] for row in rows])
    connected = np.asarray([row["connected_area_ratio"] for row in rows])
    recast_binary = next((PACKAGE / "recast").glob("recast*.so"))
    thresholds = {
        "domain": "urban",
        "reference_count": len(rows),
        "percentile": 5,
        "navigable_area_ratio": float(np.percentile(navigable, 5)),
        "connected_area_ratio": float(np.percentile(connected, 5)),
        "reference_definitions_sha256": sha256(definitions),
        "agent_sha256": sha256(PROTOCOL / "agent.json"),
        "recast_sha256": sha256(recast_binary),
    }
    atomic_json(PROTOCOL / "reference_thresholds.json", thresholds)
    result = {
        "suite": "independent deterministic valid urban pedestrian-network reference suite",
        "thresholds": thresholds,
        "summary": {
            "navigable_min": float(navigable.min()),
            "navigable_median": float(np.median(navigable)),
            "navigable_max": float(navigable.max()),
            "connected_min": float(connected.min()),
            "connected_median": float(np.median(connected)),
            "connected_max": float(connected.max()),
        },
        "scenes": rows,
    }
    atomic_json(PACKAGE / "results/reference_urban_calibration.json", result)
    print(json.dumps(thresholds, indent=2))


if __name__ == "__main__":
    main()
