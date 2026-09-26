#!/usr/bin/env python3
"""Compose all full-13 all-Eevee layers by native 32-bit camera depth."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVISION = "urban_v1_full_14"
CITY = ROOT / "infinigen/outputs/outdoor_full_demo" / REVISION
BASE_PATH = ROOT / "scripts/compose_urban_v1_full_12_zdepth.py"
os.environ.setdefault(
    "C2W_FULL12_COMPOSE_FORCE", os.environ.get("C2W_FULL14_COMPOSE_FORCE", "0")
)

spec = importlib.util.spec_from_file_location("full14_compositor_base", BASE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot import {BASE_PATH}")
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)

base.REVISION = REVISION
base.CITY = CITY
base.BLEND = CITY / f"{REVISION}.blend"
base.LAYOUT = CITY / "layout_plan.json"
base.LAYER_ROOT = CITY / "renders/zdepth_layers"
base.COMPOSITE_ROOT = CITY / "renders/zdepth_composites"
base.DELIVERY_ROOT = CITY / "renders"
base.MANIFEST_PATH = base.DELIVERY_ROOT / "render_manifest.json"
base.PANORAMA_PATH = CITY / "panorama_audit.json"
base.RENDERER_PATH = ROOT / "scripts/render_urban_v1_full_14_daytime.py"
base.LAYER_PATH = ROOT / "scripts/render_urban_v1_full_14_zdepth_layer.py"

# Every source frame, including the common base, is Eevee.  The existing
# receiver-ratio branch therefore compares each Combined frame with the same
# camera's Eevee Base frame; no Workbench pixel participates in delivery.
layer_spec = importlib.util.spec_from_file_location(
    "full14_compositor_layer_keys", base.LAYER_PATH
)
if layer_spec is None or layer_spec.loader is None:
    raise RuntimeError(f"Cannot inspect {base.LAYER_PATH}")
layer_keys = importlib.util.module_from_spec(layer_spec)
sys.modules[layer_spec.name] = layer_keys
layer_spec.loader.exec_module(layer_keys)
base.EEVEE_FALLBACK_LAYERS = set(layer_keys.LAYERS)
base.EEVEE_FALLBACK_BASE_ROOT = base.LAYER_ROOT / "base"
base.ALL_EEVEE_DIRECT_RECEIVER = True

_original_setup_scene = base.setup_scene


def setup_scene(renderer):
    scene = _original_setup_scene(renderer)
    # Match the physical full-13 source renders.  The inherited full-12
    # compositor used +0.35 EV for a Workbench delivery, washing out these
    # all-Eevee PBR layers and violating the identical-color-management gate.
    scene.view_settings.exposure = -0.10
    return scene


base.setup_scene = setup_scene

_original_manifest = base.build_manifest


def build_manifest(renderer, layer_module, records, started, status, errors):
    payload = _original_manifest(
        renderer, layer_module, records, started, status, errors
    )
    layout = __import__("json").loads(base.LAYOUT.read_text(encoding="utf8"))
    payload.update(
        {
            "schema": "agent.full14.zdepth_delivery.v1",
            "run_id": layout["run_id"],
            "scene_revision": REVISION,
            "material_fidelity_policy": "all source layers and common receivers rasterized in one Eevee PBR configuration; no Workbench final frames",
            "cross_layer_lighting": "same-camera native Eevee receiver selected by maximum RGB departure from the common receiver, preserving authored coplanar surfaces and physical shadows without divide extrema; identical sky, sun, exposure, color management and target grid",
            "workbench_final_frame_count": 0,
            "all_source_frames_pbr_eevee": all(
                settings.get("engine") in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}
                for frames in base.SOURCE_LAYER_FRAME_SETTINGS.values()
                for settings in frames.values()
            ),
        }
    )
    payload["render_settings"].update(
        {
            "engine": "BLENDER_EEVEE",
            "samples": 64,
            "workbench_antialiasing_samples": None,
            "workbench_color_type": None,
            "workbench_studio_light": None,
            "workbench_shadows_and_cavity": None,
            "lighting": "Nishita physical daylight plus directional sun; identical in every exact layer",
            "daytime_sky": "Nishita physical sky evaluated in Eevee",
            "view_transform": "AgX",
            "look": "AgX - Medium High Contrast",
            "exposure": -0.10,
            "all_eevee_native_combined_receiver": True,
            "receiver_lighting_division": False,
            "coplanar_receiver_policy": "strongest absolute RGB receiver contribution per pixel before exact camera-Z asset composition",
        }
    )
    return payload


base.build_manifest = build_manifest

_original_panorama = base.write_panorama_audit


def write_panorama_audit(renderer, manifest):
    _original_panorama(renderer, manifest)
    import json

    payload = json.loads(base.PANORAMA_PATH.read_text(encoding="utf8"))
    payload.update(
        {
            "schema": "agent.full14.panorama_audit.zdepth.v1",
            "run_id": manifest["run_id"],
            "scene_revision": REVISION,
            "all_source_frames_pbr_eevee": manifest["all_source_frames_pbr_eevee"],
            "workbench_final_frame_count": 0,
        }
    )
    base.atomic_json(base.PANORAMA_PATH, payload)


base.write_panorama_audit = write_panorama_audit


if __name__ == "__main__":
    base.main()
