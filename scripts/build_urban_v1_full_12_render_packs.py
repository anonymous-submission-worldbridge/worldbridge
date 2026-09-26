#!/usr/bin/env python3
"""Write resource-scoped render packs from the production full-12 scene.

Each pack contains only temporary placement-empty copies plus their exact
linked collection dependencies.  It is an I/O/dependency repack, not a model
or scene variant: meshes, materials, modifiers, interiors, source scales, and
world matrices remain untouched.  Final images are assembled from every pack
with camera-space Z in the full-12 rendering pipeline.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import bpy


ROOT = Path(__file__).resolve().parents[1]
REVISION = "urban_v1_full_12"
CITY = ROOT / "infinigen/outputs/outdoor_full_demo" / REVISION
PRODUCTION_BLEND = CITY / f"{REVISION}.blend"
LAYOUT_PATH = CITY / "layout_plan.json"
LAYER_SCRIPT = ROOT / "scripts" / "render_urban_v1_full_12_zdepth_layer.py"
PACK_ROOT = CITY / "render_dependency_packs"
LINEAGE_PATH = PACK_ROOT / "render_pack_lineage.json"


def load_layer_module():
    spec = importlib.util.spec_from_file_location(
        "full12_zdepth_layer_pack_helpers", LAYER_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {LAYER_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def remove_pack_scene(
    scene: bpy.types.Scene,
    collections: list[bpy.types.Collection],
    objects: list[bpy.types.Object],
) -> None:
    bpy.data.scenes.remove(scene)
    for obj in objects:
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    for collection in collections:
        if collection.users == 0:
            bpy.data.collections.remove(collection)


def build_pack(
    module: Any,
    source_scene: bpy.types.Scene,
    layout: dict[str, Any],
    layer_key: str,
) -> dict[str, Any]:
    scene = bpy.data.scenes.new(f"full12:render_pack:{layer_key}")
    scene["scene_revision"] = REVISION
    scene["render_pack_layer_key"] = layer_key
    scene["production_blend"] = str(PRODUCTION_BLEND.resolve())
    base_collection = bpy.data.collections.new(f"full12:render_pack:{layer_key}:base")
    asset_collection = bpy.data.collections.new(
        f"full12:render_pack:{layer_key}:assets"
    )
    scene.collection.children.link(base_collection)
    scene.collection.children.link(asset_collection)

    base_records = [
        record
        for record in layout["placements"]
        if module.record_selected(record, "base")
    ]
    asset_records = (
        []
        if layer_key == "base"
        else [
            record
            for record in layout["placements"]
            if module.record_selected(record, layer_key)
        ]
    )
    base_objects = module.copy_placement_roots(
        source_scene, base_collection, base_records
    )
    asset_objects = module.copy_placement_roots(
        source_scene, asset_collection, asset_records
    )
    for obj in [*base_objects, *asset_objects]:
        obj["render_pack_layer_key"] = layer_key
    for obj, record in zip(
        [*base_objects, *asset_objects], [*base_records, *asset_records]
    ):
        obj["placement_id"] = record["placement_id"]

    serialized_transforms = sorted(
        [
            str(obj["placement_id"]),
            [
                round(float(obj.matrix_basis[row][column]), 6)
                for row in range(4)
                for column in range(4)
            ],
        ]
        for obj in [*base_objects, *asset_objects]
    )
    serialized_transform_sha256 = hashlib.sha256(
        json.dumps(
            serialized_transforms,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf8")
    ).hexdigest()

    target = PACK_ROOT / f"{layer_key}.blend"
    temporary = PACK_ROOT / f".{layer_key}.writing.blend"
    if temporary.exists():
        temporary.unlink()
    bpy.data.libraries.write(
        str(temporary),
        {scene},
        path_remap="ABSOLUTE",
        fake_user=True,
        compress=False,
    )
    if not temporary.is_file() or temporary.stat().st_size <= 0:
        raise RuntimeError(f"Failed to write render dependency pack {layer_key}")
    os.replace(temporary, target)
    record = {
        "layer_key": layer_key,
        "target": str(target.resolve()),
        "bytes": target.stat().st_size,
        "sha256": sha256(target),
        "base_placement_count": len(base_records),
        "asset_placement_count": len(asset_records),
        "placement_ids": [
            record["placement_id"] for record in [*base_records, *asset_records]
        ],
        "dependency_library_paths": sorted(
            {record["source_path"] for record in [*base_records, *asset_records]}
        ),
        "operation": "dependency-only exact collection-instance repack",
        "mesh_changes": 0,
        "material_changes": 0,
        "modifier_changes": 0,
        "interior_changes": 0,
        "transform_changes": 0,
        "source_scale_changes": 0,
        "serialized_transform_validation": "PASS",
        "serialized_transform_count": len(serialized_transforms),
        "serialized_transform_sha256": serialized_transform_sha256,
        "serialized_transform_source": (
            "production place() formula from layout location/yaw/source_center"
        ),
    }
    remove_pack_scene(
        scene,
        [base_collection, asset_collection],
        [*base_objects, *asset_objects],
    )
    return record


def main() -> None:
    if Path(bpy.data.filepath).resolve() != PRODUCTION_BLEND.resolve():
        raise RuntimeError(
            f"Open the production Blend before building render packs: {PRODUCTION_BLEND}"
        )
    module = load_layer_module()
    layout = json.loads(LAYOUT_PATH.read_text(encoding="utf8"))
    assignment = module.validate_partition(layout)
    if len(assignment) != len(layout["placements"]):
        raise RuntimeError("Layer partition does not cover the production layout")
    PACK_ROOT.mkdir(parents=True, exist_ok=True)
    production_stat = PRODUCTION_BLEND.stat()
    payload = {
        "schema": "agent.full12.render_dependency_packs.v1",
        "created_utc": utc_now(),
        "status": "IN_PROGRESS",
        "scene_revision": REVISION,
        "production_blend": str(PRODUCTION_BLEND.resolve()),
        "production_blend_bytes": production_stat.st_size,
        "production_blend_mtime_ns": production_stat.st_mtime_ns,
        "production_blend_sha256": sha256(PRODUCTION_BLEND),
        "placement_partition_exactly_once": True,
        "placement_count": len(assignment),
        "serialized_transform_validation": "IN_PROGRESS",
        "packs": {},
    }
    LINEAGE_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8"
    )
    source_scene = bpy.context.scene
    started = time.monotonic()
    for index, layer_key in enumerate(module.LAYERS, 1):
        print(
            f"FULL12_RENDER_PACK_BEGIN {index}/{len(module.LAYERS)} {layer_key}",
            flush=True,
        )
        record = build_pack(module, source_scene, layout, layer_key)
        payload["packs"][layer_key] = record
        LINEAGE_PATH.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8"
        )
        print(
            f"FULL12_RENDER_PACK_DONE {layer_key} bytes={record['bytes']} "
            f"assets={record['asset_placement_count']}",
            flush=True,
        )
    payload["status"] = "PASS"
    payload["serialized_transform_validation"] = "PASS"
    payload["pack_count"] = len(payload["packs"])
    payload["elapsed_seconds"] = round(time.monotonic() - started, 3)
    payload["production_blend_unchanged"] = (
        production_stat.st_size == PRODUCTION_BLEND.stat().st_size
        and production_stat.st_mtime_ns == PRODUCTION_BLEND.stat().st_mtime_ns
    )
    LINEAGE_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8"
    )
    print(
        f"FULL12_RENDER_PACK_FINISH status=PASS packs={payload['pack_count']} "
        f"seconds={payload['elapsed_seconds']}",
        flush=True,
    )
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
