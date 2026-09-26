#!/usr/bin/env python3
"""Render one bounded, direct multi-layer reference in a single Eevee scene."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CITY = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13"
DIRECT_ROOT = CITY / "renders/direct_validation_layers"
os.environ["C2W_FULL13_LAYER_ROOT"] = str(DIRECT_ROOT)

if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
from urban_v1_full_13_direct_specs import DIRECT_VALIDATIONS


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    tokens = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(tokens) < 2:
        raise RuntimeError("Expected direct validation key and its contracted shot")
    key = tokens[0].removeprefix("layer:").strip().lower()
    if key not in DIRECT_VALIDATIONS:
        raise RuntimeError(f"Unknown direct validation {key}")
    expected_shot = DIRECT_VALIDATIONS[key]["shot"]
    if tokens[1:] != [expected_shot]:
        raise RuntimeError(f"{key} must render exactly {expected_shot}")

    layer = load(
        ROOT / "scripts/render_urban_v1_full_13_zdepth_layer.py",
        "full13_direct_validation_layer",
    )
    layout = json.loads((CITY / "layout_plan.json").read_text(encoding="utf8"))
    selected = {
        record["placement_id"]
        for record in layout["placements"]
        if any(
            layer.record_selected(record, source_layer)
            for source_layer in DIRECT_VALIDATIONS[key]["layers"]
        )
    }
    layer.base.LAYER_SPECS[key] = {"placement_ids": selected}

    def direct_partition(current_layout):
        assignment = {}
        for record in current_layout["placements"]:
            placement_id = record["placement_id"]
            if layer.record_selected(record, "base"):
                assignment[placement_id] = "base"
            elif placement_id in selected:
                assignment[placement_id] = key
            else:
                assignment[placement_id] = "excluded_from_bounded_direct_reference"
        return assignment

    direct_manifest = json.loads(
        (CITY / "render_dependency_packs/direct_validation_packs.json").read_text(
            encoding="utf8"
        )
    )
    dependency_hash = direct_manifest["packs"][key]["dependency_hash"]

    def direct_dependency_hash(layer_key):
        if layer_key != key:
            raise RuntimeError(f"Unexpected direct layer key {layer_key}")
        return dependency_hash

    layer.base.validate_partition = direct_partition
    layer.base.frame_dependency_hash = direct_dependency_hash
    layer.frame_dependency_hash = direct_dependency_hash

    # Every bounded direct reference is a non-base asset scene and writes the
    # same authoritative CombinedColor/CombinedDepth parts as a standard asset
    # partition.  Adapt only the layer label accepted by the shared processor;
    # pixels, parts, native resolution, and validation thresholds are unchanged.
    standard_authoritative_bundle = layer.base.authoritative_bundle_from_render

    def direct_authoritative_bundle(layer_key, raw_outputs, resolution):
        if layer_key != key:
            raise RuntimeError(f"Unexpected direct validation layer {layer_key}")
        outputs, validation = standard_authoritative_bundle(
            "full13_unique_urban_fabric", raw_outputs, resolution
        )
        validation["validator_layer_alias"] = validation.get("layer")
        validation["layer"] = key
        validation["direct_non_base_combined_parts_contract"] = True
        return outputs, validation

    layer.base.authoritative_bundle_from_render = direct_authoritative_bundle

    # The shared layer writer quite correctly expects all 80 delivery cameras
    # for a normal partition.  A bounded direct reference has a different,
    # explicit contract: exactly one named camera.  Adapt the manifest at the
    # writer boundary so successful direct renders are never left looking like
    # unfinished 1/80 standard layers.
    standard_write_manifest = layer.base.write_manifest

    def write_direct_manifest(layer_key, payload):
        if layer_key != key:
            raise RuntimeError(f"Unexpected direct validation layer {layer_key}")
        views = [
            record
            for record in payload.get("views", [])
            if record.get("name") == expected_shot
        ]
        errors = payload.get("errors", [])
        completed = len(views) == 1 and views[0].get("status") == "rendered"
        payload["views"] = views
        payload["requested_view_names"] = [expected_shot]
        payload["completed_view_names"] = [expected_shot] if completed else []
        payload["completed_count"] = 1 if completed else 0
        payload["expected_count"] = 1
        payload["complete"] = bool(completed and not errors)
        payload["status"] = (
            "PASS" if payload["complete"] else ("FAIL" if errors else "IN_PROGRESS")
        )
        payload["direct_validation_contract"] = {
            "type": "bounded_multi_layer_single_camera_reference",
            "key": key,
            "shot": expected_shot,
            "source_layers": list(DIRECT_VALIDATIONS[key]["layers"]),
            "expected_count": 1,
        }
        standard_write_manifest(layer_key, payload)

    layer.base.write_manifest = write_direct_manifest
    layer.base.main()


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)
