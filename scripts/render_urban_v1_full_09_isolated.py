"""Read-only bounded renderer for the source-generated FULL09 checkpoint.

The generator owns all camera creation and scene content.  This worker opens
that result, renders only requested/missing cameras, and never saves the Blend.
Use ``C2W_VALIDATION_CAMERAS`` for a comma-separated batch and
``C2W_RENDER_ENGINE=BLENDER_EEVEE_NEXT`` only for diagnostic previews; the
production default is Cycles.
"""
from __future__ import annotations

# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths["WORLDBRIDGE_ROOT"]


import json
import os
import time
from pathlib import Path

import bpy


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_09"


def configure_render() -> dict:
    scene = bpy.context.scene
    engine = os.environ.get("C2W_RENDER_ENGINE", "CYCLES")
    scene.render.engine = engine
    device = "CPU"
    if engine == "CYCLES":
        requested = os.environ.get("C2W_RENDER_DEVICE", "GPU").upper()
        if requested == "GPU":
            try:
                preferences = bpy.context.preferences.addons["cycles"].preferences
                preferences.compute_device_type = "OPTIX"
                preferences.get_devices()
                enabled = []
                for item in preferences.devices:
                    item.use = item.type != "CPU"
                    if item.use:
                        enabled.append(f"{item.type}:{item.name}")
                if not enabled:
                    raise RuntimeError("Cycles reported no non-CPU devices")
                scene.cycles.device = "GPU"
                device = ", ".join(enabled)
            except Exception as exc:
                scene.cycles.device = "CPU"
                device = f"CPU fallback ({exc})"
        else:
            scene.cycles.device = "CPU"
        scene.cycles.samples = int(os.environ.get("C2W_RENDER_SAMPLES", "16"))
        scene.cycles.use_denoising = True
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.adaptive_threshold = 0.035
        scene.cycles.max_bounces = 5
        scene.cycles.diffuse_bounces = 2
        scene.cycles.glossy_bounces = 2
        scene.cycles.transmission_bounces = 3
        # The complete city contains more than eleven thousand render geometries.
        # Keep Cycles' scene/BVH cache while only the active camera changes;
        # otherwise every validation view rebuilds the same OptiX structures.
        scene.render.use_persistent_data = True
    scene.render.resolution_x = int(os.environ.get("C2W_RENDER_WIDTH", "1280"))
    scene.render.resolution_y = int(os.environ.get("C2W_RENDER_HEIGHT", "720"))
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.compression = 35
    scene.view_settings.look = "AgX - Medium High Contrast"
    return {
        "engine": engine,
        "device": device,
        "samples": int(scene.cycles.samples) if engine == "CYCLES" else None,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
    }


def main() -> None:
    if bpy.context.scene.get("c2w_revision") != "urban_v1_full_09":
        raise RuntimeError(
            f"Refusing non-FULL09 scene: {bpy.context.scene.get('c2w_revision')}"
        )
    requested = {
        item.strip()
        for item in os.environ.get("C2W_VALIDATION_CAMERAS", "").split(",")
        if item.strip()
    }
    cameras = sorted(
        [
            (obj, obj.name.removeprefix("full:"))
            for obj in bpy.data.objects
            if obj.type == "CAMERA"
            and obj.name.startswith("full:")
            and obj.name.endswith(".png")
        ],
        key=lambda item: item[1],
    )
    if len(cameras) != 41:
        raise RuntimeError(
            f"FULL09 expected 41 generator-owned cameras, got {len(cameras)}"
        )
    if requested:
        unknown = requested - {filename for _, filename in cameras}
        if unknown:
            raise RuntimeError(f"Unknown FULL09 render cameras: {sorted(unknown)}")
        cameras = [item for item in cameras if item[1] in requested]
    if not cameras:
        raise RuntimeError("No FULL09 render cameras selected")

    settings = configure_render()
    print(
        f"[Full09Render] settings={json.dumps(settings, ensure_ascii=False)}",
        flush=True,
    )
    rendered = []
    for camera, filename in cameras:
        target = OUT / filename
        if target.is_file() and target.stat().st_size > 100_000:
            print(f"[Full09Render] existing={filename}", flush=True)
            continue
        started = time.time()
        bpy.context.scene.camera = camera
        bpy.context.scene.render.filepath = str(target)
        bpy.ops.render.render(write_still=True)
        if not target.is_file() or target.stat().st_size <= 100_000:
            raise RuntimeError(f"Render output is missing or too small: {target}")
        item = {
            "filename": filename,
            "bytes": target.stat().st_size,
            "seconds": round(time.time() - started, 2),
        }
        rendered.append(item)
        print(
            f"[Full09Render] rendered={json.dumps(item, ensure_ascii=False)}",
            flush=True,
        )
    print(f"[Full09Render] complete new_frames={len(rendered)}", flush=True)


if __name__ == "__main__":
    main()
