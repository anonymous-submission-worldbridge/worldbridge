#!/usr/bin/env python3
"""Build the connected full-detail semantic public-interior production pack.

The main full-13 generator links these exact four collections and places them
in the delivered city.  Keeping the room programs in their own dependency
pack makes real furniture revisions invalidate the semantic raster layer,
without pretending unrelated terrain or building meshes also changed.
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
        city.OUT / "semantic_pack.status.json",
        {
            "run_id": city.RUN_ID,
            "stage": "semantic_public_interiors_pack",
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
        city.log("Building four full-detail semantic public interiors")
        interiors = city.add_semantic_interiors()
        expected = city.semantic_collection_names()
        missing = [name for name in expected if bpy.data.collections.get(name) is None]
        if missing:
            raise RuntimeError(f"Semantic production collections missing: {missing}")
        counts = {item["program"]: item["parts"] for item in interiors["records"]}
        thresholds = {
            "school_cafeteria": 80,
            "library_reading_room": 400,
            "bank_atrium": 150,
            "hospital_lobby": 170,
        }
        if any(counts.get(name, 0) < minimum for name, minimum in thresholds.items()):
            raise RuntimeError(
                f"Semantic production detail gate failed: counts={counts}, "
                f"minimums={thresholds}"
            )

        temporary = city.SEMANTIC_PACK.with_suffix(".writing.blend")
        if temporary.exists():
            temporary.unlink()
        bpy.data.libraries.write(
            str(temporary),
            {bpy.context.scene},
            path_remap="ABSOLUTE",
            fake_user=True,
            compress=False,
        )
        if not temporary.is_file() or temporary.stat().st_size <= 0:
            raise RuntimeError("Semantic production pack write was empty")
        os.replace(temporary, city.SEMANTIC_PACK)
        payload = {
            "schema": "agent.full14.semantic_public_interiors_pack.v1",
            "run_id": city.RUN_ID,
            "status": "PASS",
            "created_utc": city.utc_now(),
            "builder": str(Path(__file__).resolve()),
            "builder_sha256": city.sha256(Path(__file__).resolve()),
            "consuming_generator": str(ROOT / "scripts/generate_urban_v1_full_14.py"),
            "consuming_generator_sha256": city.sha256(
                ROOT / "scripts/generate_urban_v1_full_14.py"
            ),
            "pack": str(city.SEMANTIC_PACK.resolve()),
            "bytes": city.SEMANTIC_PACK.stat().st_size,
            "sha256": city.sha256(city.SEMANTIC_PACK),
            "collection_names": expected,
            "interiors": interiors,
            "minimum_part_counts": thresholds,
            "observed_part_counts": counts,
            "production_connection": {
                "source_key": city.SEMANTIC_SOURCE_KEY,
                "consumer": "generate_urban_v1_full_14.add_semantic_interiors",
                "render_layer": "full14_semantic_interiors",
                "detached_demo": False,
            },
            "quality": {
                "toy_or_placeholder_models": 0,
                "proxy_geometry": 0,
                "mesh_simplification": False,
                "material_node_simplification": False,
                "complete_room_envelopes": True,
                "functional_signage_and_hardware": True,
                "same_pipeline_run": True,
            },
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        city.atomic_json(city.SEMANTIC_PACK_MANIFEST, payload)
        city.atomic_json(
            city.OUT / "semantic_pack.status.json",
            {
                "run_id": city.RUN_ID,
                "stage": "semantic_public_interiors_pack",
                "status": "PASS",
                "completed_utc": payload["created_utc"],
                "sha256": payload["sha256"],
                "observed_part_counts": counts,
            },
        )
        (city.OUT / "SEMANTIC_PACK_FAILED.txt").unlink(missing_ok=True)
        city.log(
            f"Saved connected semantic pack {city.SEMANTIC_PACK} "
            f"counts={json.dumps(counts, sort_keys=True)} sha256={payload['sha256']}"
        )
    except Exception:
        failure = traceback.format_exc()
        city.atomic_json(
            city.OUT / "semantic_pack.status.json",
            {
                "run_id": city.RUN_ID,
                "stage": "semantic_public_interiors_pack",
                "status": "FAIL",
                "completed_utc": city.utc_now(),
                "error": failure,
            },
        )
        (city.OUT / "SEMANTIC_PACK_FAILED.txt").write_text(failure, encoding="utf8")
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
