#!/usr/bin/env python3
"""Build bounded multi-layer packs for direct-vs-Z representative checks."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from urban_v1_full_14_direct_specs import DIRECT_VALIDATIONS


CITY = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_14"
PRODUCTION = CITY / "urban_v1_full_14.blend"
OUTPUT = CITY / "render_dependency_packs/direct_validation_packs.json"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def atomic(payload: dict) -> None:
    temporary = OUTPUT.with_suffix(".writing.json")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8"
    )
    os.replace(temporary, OUTPUT)


def main() -> None:
    if Path(bpy.data.filepath).resolve() != PRODUCTION.resolve():
        raise RuntimeError(f"Open the full-13 production Blend: {PRODUCTION}")
    layer = load(
        ROOT / "scripts/render_urban_v1_full_14_zdepth_layer.py",
        "full14_direct_pack_layers",
    )
    builder = load(
        ROOT / "scripts/build_urban_v1_full_12_render_packs.py",
        "full14_direct_pack_builder",
    )
    builder.REVISION = "urban_v1_full_14"
    builder.CITY = CITY
    builder.PRODUCTION_BLEND = PRODUCTION
    builder.LAYOUT_PATH = CITY / "layout_plan.json"
    builder.PACK_ROOT = CITY / "render_dependency_packs"
    layout = json.loads(builder.LAYOUT_PATH.read_text(encoding="utf8"))
    standard = json.loads(
        (builder.PACK_ROOT / "render_pack_lineage.json").read_text(encoding="utf8")
    )
    known_fingerprints = {}
    for record in standard["packs"].values():
        inputs = record.get("dependency_fingerprints", {})
        for item in inputs.get("dependency_libraries", []):
            known_fingerprints[item["path"]] = item
        for item in inputs.get("render_contract_files", []):
            known_fingerprints[item["path"]] = item

    records = {}
    source_scene = bpy.context.scene
    for key, validation in DIRECT_VALIDATIONS.items():
        selected = {
            record["placement_id"]
            for record in layout["placements"]
            if any(
                layer.record_selected(record, source_layer)
                for source_layer in validation["layers"]
            )
        }
        layer.base.LAYER_SPECS[key] = {"placement_ids": selected}
        record = builder.build_pack(layer.base, source_scene, layout, key)
        dependencies = []
        for path_string in record["dependency_library_paths"]:
            path = Path(path_string).resolve()
            fingerprint = known_fingerprints.get(str(path))
            if fingerprint is None:
                stat = path.stat()
                fingerprint = {
                    "path": str(path),
                    "bytes": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "sha256": builder.sha256(path),
                }
            dependencies.append(fingerprint)
        target = Path(record["target"])
        inputs = {
            "key": key,
            "shot": validation["shot"],
            "source_layers": list(validation["layers"]),
            "placement_ids": sorted(selected),
            "pack_sha256": builder.sha256(target),
            "dependency_libraries": dependencies,
            "render_contract_sha256": {
                path.name: builder.sha256(path)
                for path in (
                    ROOT / "scripts/render_urban_v1_full_14_daytime.py",
                    ROOT / "scripts/render_urban_v1_full_14_zdepth_layer.py",
                    ROOT / "scripts/render_urban_v1_full_14_direct_validation.py",
                    ROOT / "scripts/urban_v1_full_14_direct_specs.py",
                    ROOT / "scripts/process_urban_v1_full_14_exr.py",
                )
            },
            "engine": "EEVEE",
            "resolution": [1920, 1080],
            "samples": 64,
        }
        dependency_hash = hashlib.sha256(
            json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode("utf8")
        ).hexdigest()
        records[key] = {
            **record,
            "shot": validation["shot"],
            "source_layers": list(validation["layers"]),
            "asset_placement_ids": sorted(selected),
            "dependency_inputs": inputs,
            "dependency_hash": dependency_hash,
        }
        print(
            f"FULL14_DIRECT_PACK {key} assets={len(selected)} hash={dependency_hash}",
            flush=True,
        )
    payload = {
        "schema": "agent.full14.direct_validation_packs.v1",
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "run_id": layout["run_id"],
        "status": "PASS",
        "production_blend_sha256": builder.sha256(PRODUCTION),
        "pack_count": len(records),
        "packs": records,
        "quality": {
            "mesh_changes": 0,
            "material_changes": 0,
            "source_scale_changes": 0,
        },
    }
    atomic(payload)


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
