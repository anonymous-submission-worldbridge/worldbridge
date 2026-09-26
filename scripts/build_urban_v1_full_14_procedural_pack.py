#!/usr/bin/env python3
"""Build the same-run production-detail dependency pack for full-13.

This is stage 1 of the integrated full-13 pipeline, not a renderable demo.
The main generator links these exact collections into the production city.
Separating authoring from the 34 GiB external dependency load bounds peak RAM
without simplifying a mesh or material.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
os.environ["C2W_FULL14_BUILD_PROCEDURAL_PACK"] = "1"

import generate_urban_v1_full_14 as city


def main() -> None:
    city.OUT.mkdir(parents=True, exist_ok=True)
    city.PACK_OUT.mkdir(parents=True, exist_ok=True)
    city.atomic_json(
        city.OUT / "procedural_pack.status.json",
        {
            "run_id": city.RUN_ID,
            "stage": "procedural_pack",
            "status": "RUNNING",
            "started_utc": city.utc_now(),
            "builder": str(Path(__file__).resolve()),
        },
    )
    started = time.monotonic()
    try:
        city.framework.reset_scene()
        city.framework.ZONES.clear()
        city.framework.PLACEMENTS.clear()
        city.log("Building bounded PBR ground master")
        city.add_compact_ground()
        city.log(
            "Building physically continuous full-detail PBR substrate under complete source-road modules"
        )
        road_substrate = city.add_connected_road_substrate()
        city.log(
            "Building multi-frequency perimeter terrain, individually meshed articulated broadleaf trees, and continued boundary roads"
        )
        perimeter_landscape = city.add_perimeter_context_landscape()
        city.log(
            "Building six detailed tree masters and forty-eight varied inner-greenbelt instances"
        )
        urban_tree_instances = city.add_instanced_inner_greenbelt()
        city.log("Building twenty unique all45_02 four-sided production buildings")
        infill = city.add_unique_urban_fabric()
        city.log(
            "Building continuous paths, factory pedestrians, and detailed bicycles"
        )
        activity = city.add_public_realm_and_activity()
        city.log("Building the complete audited-entrance connector network")
        connector_network = city.add_complete_entrance_connector_network()
        missing = [
            name
            for name in city.procedural_collection_names()
            if bpy.data.collections.get(name) is None
        ]
        if missing:
            raise RuntimeError(f"Procedural pack collections missing: {missing}")
        temporary = city.PROCEDURAL_PACK.with_suffix(".writing.blend")
        if temporary.exists():
            temporary.unlink()
        bpy.data.libraries.write(
            str(temporary),
            {bpy.context.scene},
            path_remap="ABSOLUTE",
            fake_user=True,
            compress=False,
        )
        if temporary.stat().st_size <= 0:
            raise RuntimeError("Procedural pack write was empty")
        os.replace(temporary, city.PROCEDURAL_PACK)
        payload = {
            "schema": "agent.full14.same_run_procedural_pack.v1",
            "run_id": city.RUN_ID,
            "status": "PASS",
            "created_utc": city.utc_now(),
            "builder": str(Path(__file__).resolve()),
            "builder_sha256": city.sha256(Path(__file__).resolve()),
            "consuming_generator": str(ROOT / "scripts/generate_urban_v1_full_14.py"),
            "consuming_generator_sha256": city.sha256(
                ROOT / "scripts/generate_urban_v1_full_14.py"
            ),
            "pack": str(city.PROCEDURAL_PACK.resolve()),
            "bytes": city.PROCEDURAL_PACK.stat().st_size,
            "sha256": city.sha256(city.PROCEDURAL_PACK),
            "collection_names": city.procedural_collection_names(),
            "infill": infill,
            "interiors": {
                "status": "SPLIT_TO_CONNECTED_SEMANTIC_PACK",
                "pack": str(city.SEMANTIC_PACK.resolve()),
                "manifest": str(city.SEMANTIC_PACK_MANIFEST.resolve()),
                "reason": "semantic interiors have an independent render dependency boundary",
            },
            "activity": {
                "genuine_infinigen_pedestrian_count": activity["pedestrians"],
                "pedestrian_part_count": activity["pedestrian_parts"],
                "detailed_bicycle_count": activity["bicycles"],
                "accessible_path_count": activity["accessible_links"],
                "minimum_path_width_m": activity["minimum_path_width_m"],
            },
            "road_substrate": road_substrate,
            "perimeter_landscape": perimeter_landscape,
            "urban_tree_instances": urban_tree_instances,
            "connector_network": connector_network,
            "quality": {
                "toy_or_placeholder_models": 0,
                "proxy_geometry": 0,
                "mesh_simplification": False,
                "material_node_simplification": False,
                "same_pipeline_run": True,
            },
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        city.atomic_json(city.PROCEDURAL_PACK_MANIFEST, payload)
        city.atomic_json(
            city.OUT / "procedural_pack.status.json",
            {
                "run_id": city.RUN_ID,
                "stage": "procedural_pack",
                "status": "PASS",
                "completed_utc": payload["created_utc"],
                "sha256": payload["sha256"],
            },
        )
        (city.OUT / "PROCEDURAL_PACK_FAILED.txt").unlink(missing_ok=True)
        city.log(
            f"Saved integrated procedural pack {city.PROCEDURAL_PACK} "
            f"bytes={payload['bytes']} sha256={payload['sha256']}"
        )
    except Exception:
        failure = traceback.format_exc()
        city.atomic_json(
            city.OUT / "procedural_pack.status.json",
            {
                "run_id": city.RUN_ID,
                "stage": "procedural_pack",
                "status": "FAIL",
                "completed_utc": city.utc_now(),
                "error": failure,
            },
        )
        (city.OUT / "PROCEDURAL_PACK_FAILED.txt").write_text(failure, encoding="utf8")
        raise


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
